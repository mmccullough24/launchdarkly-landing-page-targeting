"""ABC Company dashboard — a LaunchDarkly release-safety demo.

Run it with:  python app.py     (see README.md for full setup)

What this file wires together:

* `/`                    renders the dashboard for a chosen persona, with the
                         feature flag evaluated server-side.
* `/api/stream`          a Server-Sent Events stream. The browser holds it open;
                         when the flag changes, the freshly rendered panel is
                         pushed down it and swapped in with no page reload.
* `/api/report-bug`      sends a custom metric event to LaunchDarkly — the
                         signal that would tell you a release is going wrong.
* `/api/remediate`       fires the kill switch (trigger URL or REST API).
* `/api/self-test/*`     only active in the offline self-test mode.
"""

import json
import logging
import queue
import sys
import uuid
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

import config
import ld_integration
import personas
import remediation
from features import order_insights
from session_hub import Session, SessionHub

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("abc.dashboard")

app = Flask(__name__)
hub = SessionHub()

# How long the SSE loop waits for an update before emitting a keep-alive comment.
# Keep-alives stop proxies and browsers from dropping an idle connection.
_SSE_HEARTBEAT_SECONDS = 15


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_panel(flag_on: bool) -> str:
    """Render whichever version of the feature the flag selected.

    Called from request threads *and* from LaunchDarkly's listener thread, so it
    pushes an application context explicitly (nesting one is harmless).
    """
    view = order_insights.build_view(flag_on)
    template = "panels/order_insights_v2.html" if flag_on else "panels/order_insights_legacy.html"
    with app.app_context():
        return render_template(template, view=view)


def build_state(persona_id: str, flag_on: bool | None = None, source: str = "initial") -> dict:
    """Assemble everything the browser needs to display the current state.

    The flag is always re-evaluated so the UI can show *why* the value is what
    it is ("flag turned off" vs "matched a targeting rule"). `flag_on`, when the
    listener supplies it, is the authoritative value for the change that just
    fired, so it wins over the re-read.
    """
    persona = personas.PERSONAS[persona_id]
    context = personas.build_context(persona_id)

    evaluation = ld_integration.evaluate(context)
    if flag_on is not None:
        evaluation["value"] = flag_on

    return {
        "flagKey": config.FLAG_KEY,
        "flagValue": evaluation["value"],
        "reasonKind": evaluation["reasonKind"],
        "reasonText": evaluation["reasonText"],
        "isFallback": evaluation["isFallback"],
        "persona": {"id": persona_id, **persona},
        "variantLabel": "Order Insights v2 — new" if evaluation["value"] else "Order Insights v1 — current",
        "panelHtml": render_panel(evaluation["value"]),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "source": source,
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    persona_id = personas.resolve_persona_id(request.args.get("user"))
    state = build_state(persona_id)
    return render_template(
        "index.html",
        state=state,
        # The panel is already rendered into the page, so leave its HTML out of
        # the JSON handed to the browser rather than shipping it twice.
        bootstrap_state={key: value for key, value in state.items() if key != "panelHtml"},
        personas=personas.PERSONAS,
        flag_key=config.FLAG_KEY,
        remediation_ready=remediation.is_configured(),
        remediation_method=remediation.describe_configuration(),
        offline_self_test=config.OFFLINE_SELF_TEST,
    )


# ---------------------------------------------------------------------------
# The live stream — this is what removes the page reload
# ---------------------------------------------------------------------------


@app.get("/api/stream")
def stream():
    """Open an SSE stream for one browser tab.

    The tab supplies its own `session` id so it can reconnect to the same
    logical session, and the persona it is currently viewing.
    """
    session_id = request.args.get("session") or uuid.uuid4().hex
    persona_id = personas.resolve_persona_id(request.args.get("user"))
    context = personas.build_context(persona_id)

    def on_flag_change(session: Session, new_value: bool) -> dict:
        """Runs on the LaunchDarkly SDK thread when the flag value changes."""
        log.info(
            "Flag '%s' changed to %s for %s — pushing to session %s",
            config.FLAG_KEY, new_value, session.persona_id, session.id,
        )
        return build_state(session.persona_id, flag_on=new_value, source="flag-change")

    session = hub.open(session_id, persona_id, context, on_flag_change)

    def event_stream():
        try:
            # Send the current state immediately so the tab is correct even if
            # the flag changed between the page render and the stream opening.
            yield _sse("state", build_state(persona_id, source="connected"))
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
# Metrics and remediation
# ---------------------------------------------------------------------------


@app.post("/api/report-bug")
def report_bug():
    """Record that a user hit a problem with the feature currently being served.

    In a real rollout this is the signal that justifies the rollback: attach the
    `order-insights-issue-reported` metric to the flag in LaunchDarkly and you
    can watch error rates per variation while the release is in flight.
    """
    persona_id = personas.resolve_persona_id(request.json.get("user") if request.is_json else None)
    context = personas.build_context(persona_id)
    state = ld_integration.evaluate(context)

    ld_integration.track(
        "order-insights-issue-reported",
        context,
        {"variant": "v2" if state["value"] else "legacy"},
    )
    log.warning("Issue reported by %s while seeing variant=%s", persona_id, state["value"])
    return jsonify({"ok": True, "message": "Issue reported to LaunchDarkly as a custom metric event."})


@app.post("/api/remediate")
def remediate():
    """Fire the kill switch: turn the release flag off for everyone, now.

    The response only reports that LaunchDarkly accepted the request. The UI
    change arrives separately, over the SSE stream, when the SDK receives the
    flag update — exactly as it would for any other client of your system.
    """
    ok, message = remediation.kill_switch()
    log.warning("Kill switch requested: ok=%s (%s)", ok, message)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 502)


@app.post("/api/restore")
def restore():
    """Turn the flag back on (REST API path only) so you can re-run the demo."""
    ok, message = remediation.restore()
    return jsonify({"ok": ok, "message": message}), (200 if ok else 502)


# ---------------------------------------------------------------------------
# Offline self-test (OFFLINE_SELF_TEST=1 only) — see README
# ---------------------------------------------------------------------------


@app.post("/api/self-test/toggle")
def self_test_toggle():
    if not config.OFFLINE_SELF_TEST:
        return jsonify({"ok": False, "message": "Offline self-test is not enabled."}), 404
    value = bool(request.json.get("value")) if request.is_json else False
    ld_integration.self_test_set_flag(value)
    return jsonify({"ok": True, "message": f"In-memory flag set to {value}."})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "sessions": hub.count(), "flagKey": config.FLAG_KEY})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 78)
    print("  ABC Company — Order Insights dashboard (LaunchDarkly demo)")
    print("=" * 78)

    if not ld_integration.initialize():
        print(
            "\n*** LaunchDarkly did not initialize.\n"
            "    Check that LAUNCHDARKLY_SDK_KEY in your .env is a valid server-side\n"
            "    SDK key (it starts with 'sdk-') and that this machine can reach\n"
            "    https://stream.launchdarkly.com. See README.md -> Troubleshooting.\n",
            file=sys.stderr,
        )
        return 1

    mode = "OFFLINE SELF-TEST (not connected to LaunchDarkly)" if config.OFFLINE_SELF_TEST else "connected to LaunchDarkly"
    print(f"  SDK status      : {mode}")
    print(f"  Feature flag    : {config.FLAG_KEY}")
    print(f"  Remediation via : {remediation.describe_configuration()}")
    print(f"  Dashboard       : http://{config.HOST}:{config.PORT}/")
    print("=" * 78, flush=True)

    try:
        # threaded=True is required: every open browser tab holds one SSE
        # connection (and therefore one worker thread) for as long as it is open.
        # use_reloader=False keeps a single SDK client per process.
        app.run(host=config.HOST, port=config.PORT, threaded=True, use_reloader=False)
    finally:
        hub.close_all()
        ld_integration.shutdown()
        print("\nLaunchDarkly client closed. Goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
