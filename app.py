"""ABC Company landing page — a LaunchDarkly targeting demo.

Run it with:  python app.py     (see README.md for full setup)

The landing page revamp is being rolled out one audience at a time. A single
LaunchDarkly flag decides which hero each visitor sees, and this app makes the
*decision* visible: for every visitor it shows which variation was served and
which targeting mechanism produced it — an individual target, a targeting rule,
or the flag's default rule.

Routes:

* `/`                     the landing page, rendered for a chosen visitor with
                          the flag evaluated server-side.
* `/api/stream`           a Server-Sent Events stream. The browser holds it
                          open; when targeting changes in LaunchDarkly the
                          freshly rendered hero is pushed down it and swapped in
                          with no page reload.
* `/api/cta-click`        sends a custom conversion metric event, so variations
                          can be compared on real signal.
* `/api/offline/*`        only active in offline demo mode.
* `/healthz`              liveness plus the number of open streams.
"""

import json
import logging
import queue
import sys
import uuid
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

import config
import contexts
import ld_client
from components import hero
from session_hub import Session, SessionHub

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("abc.landing")

app = Flask(__name__)
hub = SessionHub()

# How long the SSE loop waits for an update before emitting a keep-alive
# comment. Keep-alives stop proxies and browsers dropping an idle connection.
_SSE_HEARTBEAT_SECONDS = 15


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_hero(variation: str) -> str:
    """Render whichever hero the flag selected.

    Called from request threads *and* from LaunchDarkly's listener thread, so it
    pushes a Flask application context explicitly (nesting one is harmless).
    """
    view = hero.build_hero(variation)
    with app.app_context():
        return render_template("hero.html", hero=view)


def build_state(visitor_id: str, variation: str | None = None, source: str = "initial") -> dict:
    """Assemble everything the browser needs to render and explain the page.

    The flag is always re-evaluated so the UI can show *why* this visitor got
    this hero. When the change listener supplies `variation`, that is the
    authoritative value for the change that just fired, so it wins over the
    re-read.
    """
    visitor = contexts.VISITORS[visitor_id]
    context = contexts.build_context(visitor_id)

    evaluation = ld_client.evaluate(context)
    if variation is not None:
        evaluation["variation"] = variation

    served = evaluation["variation"]

    return {
        "flagKey": config.FLAG_KEY,
        "variation": served,
        "variationIndex": evaluation["variationIndex"],
        "mechanism": evaluation["mechanism"],
        "reasonKind": evaluation["reasonKind"],
        "reasonText": evaluation["reasonText"],
        "ruleId": evaluation["ruleId"],
        "isFallback": evaluation["isFallback"],
        "visitor": {
            "id": visitor_id,
            "key": visitor["key"],
            "name": visitor["name"],
            "title": visitor["title"],
            "blurb": visitor["blurb"],
        },
        "attributes": contexts.context_summary(visitor_id),
        # Shown side by side with the actual result so you can confirm your
        # targeting matches what the README asked you to build.
        "expected": {
            "variation": visitor["expected_variation"],
            "via": visitor["expected_via"],
            "matches": (
                served == visitor["expected_variation"]
                and evaluation["reasonKind"] == visitor["expected_via"]
            ),
        },
        "heroHtml": render_hero(served),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "source": source,
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    visitor_id = contexts.resolve_visitor_id(request.args.get("visitor"))
    state = build_state(visitor_id)
    return render_template(
        "index.html",
        state=state,
        # The hero is already rendered into the page, so leave its HTML out of
        # the JSON handed to the browser rather than shipping it twice.
        bootstrap_state={key: value for key, value in state.items() if key != "heroHtml"},
        visitors=contexts.VISITORS,
        flag_key=config.FLAG_KEY,
        offline_demo=config.OFFLINE_DEMO,
        offline_targeting_on=ld_client.offline_is_targeting_on() if config.OFFLINE_DEMO else None,
    )


# ---------------------------------------------------------------------------
# The live stream — this is what removes the page reload
# ---------------------------------------------------------------------------


@app.get("/api/stream")
def stream():
    """Open an SSE stream for one browser tab.

    The tab supplies its own `session` id and the visitor it is currently
    impersonating. Switching visitor re-opens the stream so the server registers
    a listener for the new LaunchDarkly context.
    """
    session_id = request.args.get("session") or uuid.uuid4().hex
    visitor_id = contexts.resolve_visitor_id(request.args.get("visitor"))
    context = contexts.build_context(visitor_id)

    def on_flag_change(session: Session, new_variation: str) -> dict:
        """Runs on the LaunchDarkly SDK thread when the value changes."""
        log.info(
            "Flag '%s' changed to '%s' for %s — pushing to session %s",
            config.FLAG_KEY, new_variation, session.visitor_id, session.id,
        )
        return build_state(session.visitor_id, variation=new_variation, source="flag-change")

    session = hub.open(session_id, visitor_id, context, on_flag_change)

    def event_stream():
        try:
            # Send current state immediately, so the tab is correct even if
            # targeting changed between the page render and the stream opening.
            yield _sse("state", build_state(visitor_id, source="connected"))
            while True:
                try:
                    payload = session.queue.get(timeout=_SSE_HEARTBEAT_SECONDS)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse("state", payload)
        except GeneratorExit:
            # Browser tab closed or navigated away.
            raise
        finally:
            hub.close(session_id)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tells nginx and friends not to buffer the stream.
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@app.post("/api/cta-click")
def cta_click():
    """Record that this visitor clicked the hero's primary call to action.

    This is the measurement half of a safe rollout. Attach the
    `landing-page-cta-click` metric to the flag in LaunchDarkly and you can
    compare conversion per variation while the revamp is in flight, rather than
    arguing about which hero is better.
    """
    payload = request.get_json(silent=True) or {}
    visitor_id = contexts.resolve_visitor_id(payload.get("visitor"))
    context = contexts.build_context(visitor_id)
    evaluation = ld_client.evaluate(context)

    ld_client.track(
        "landing-page-cta-click",
        context,
        {"variation": evaluation["variation"], "mechanism": evaluation["mechanism"]},
    )
    log.info("CTA click by %s on variation '%s'", visitor_id, evaluation["variation"])
    return jsonify({
        "ok": True,
        "message": f"Conversion event sent to LaunchDarkly for variation '{evaluation['variation']}'.",
    })


# ---------------------------------------------------------------------------
# Offline demo mode (OFFLINE_DEMO=1 only) — see README
# ---------------------------------------------------------------------------


@app.post("/api/offline/targeting")
def offline_targeting():
    """Turn the in-memory flag on/off, mimicking the LaunchDarkly kill switch."""
    if not config.OFFLINE_DEMO:
        return jsonify({"ok": False, "message": "Offline demo mode is not enabled."}), 404
    payload = request.get_json(silent=True) or {}
    on = bool(payload.get("on"))
    ld_client.offline_set_targeting(on)
    return jsonify({"ok": True, "message": f"Targeting turned {'on' if on else 'off'}."})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "sessions": hub.count(), "flagKey": config.FLAG_KEY})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 78)
    print("  ABC Company — landing page hero (LaunchDarkly targeting demo)")
    print("=" * 78)

    if not ld_client.initialize():
        print(
            "\n*** LaunchDarkly did not initialize.\n"
            "    Check that LAUNCHDARKLY_SDK_KEY in your .env is a valid server-side\n"
            "    SDK key (it starts with 'sdk-') and that this machine can reach\n"
            "    https://stream.launchdarkly.com.\n"
            "    No account handy? Run:  OFFLINE_DEMO=1 python app.py\n"
            "    See README.md -> Troubleshooting.\n",
            file=sys.stderr,
        )
        return 1

    mode = "OFFLINE DEMO (not connected)" if config.OFFLINE_DEMO else "connected to LaunchDarkly"
    print(f"  SDK status   : {mode}")
    print(f"  Feature flag : {config.FLAG_KEY}")
    print(f"  Variations   : {', '.join(ld_client.VARIATIONS)}")
    print(f"  Landing page : http://{config.HOST}:{config.PORT}/")
    print("=" * 78, flush=True)

    try:
        # threaded=True is required: every open browser tab holds one SSE
        # connection (and therefore one worker thread) for as long as it is open.
        # use_reloader=False keeps exactly one SDK client per process.
        app.run(host=config.HOST, port=config.PORT, threaded=True, use_reloader=False)
    finally:
        hub.close_all()
        ld_client.shutdown()
        print("\nLaunchDarkly client closed. Goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
