"""Everything this app does with the LaunchDarkly Python SDK.

Four things happen here, and they map onto the four things the demo needs to
show:

1. `initialize()`  — one long-lived, process-wide SDK client holding a streaming
                     connection, so targeting changes arrive in milliseconds.
2. `evaluate()`    — ask LaunchDarkly which hero a specific visitor should see,
                     *and why*. The "why" is what makes individual targeting and
                     rule-based targeting visible instead of implied.
3. `add_flag_value_change_listener()` — LaunchDarkly calls us when the value
                     changes for a given context, which is how the browser
                     switches heroes with no page reload.
4. `track()`       — custom metric events, so a rollout can be judged on real
                     signal rather than a hunch.
"""

import logging
from typing import Any, Callable, Optional

import ldclient
from ldclient import Context
from ldclient.config import Config
from ldclient.interfaces import FlagValueChange

import config

log = logging.getLogger(__name__)

# Keeps the SDK's own (fairly chatty) logging out of the demo output. Set this
# to logging.DEBUG if you need to watch the streaming connection handshake.
logging.getLogger("ldclient").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def initialize() -> bool:
    """Start the shared LaunchDarkly client. Returns True if it connected.

    `ldclient.set_config()` creates a singleton client and blocks for up to five
    seconds while it downloads the initial flag payload. Create it once per
    process and share it — never one client per request, which would open a
    streaming connection per request.
    """
    if config.OFFLINE_DEMO:
        _init_offline_demo()
    else:
        if not config.SDK_KEY:
            log.error("LAUNCHDARKLY_SDK_KEY is not set — see .env.example")
            return False
        # A default Config streams flag updates over a persistent connection.
        # Nothing here polls on a timer; that streaming connection is what makes
        # a targeting change show up in the browser instantly.
        ldclient.set_config(Config(config.SDK_KEY))

    return ldclient.get().is_initialized()


def shutdown() -> None:
    """Flush pending analytics events and close the connection cleanly."""
    client = ldclient.get()
    client.flush()
    client.close()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

# Maps LaunchDarkly's evaluation reason onto the targeting mechanism that
# produced it. The UI colour-codes on this, so a viewer can tell at a glance
# whether a visitor was matched *by name* or *by rule*.
_MECHANISM_BY_REASON = {
    "TARGET_MATCH": "individual",
    "RULE_MATCH": "rule",
    "FALLTHROUGH": "default",
    "OFF": "off",
    "PREREQUISITE_FAILED": "off",
    "ERROR": "error",
}


def evaluate(context: Context) -> dict:
    """Evaluate the landing page flag for one visitor.

    Uses `variation_detail()` rather than plain `variation()`. The plain call
    returns only the value; `variation_detail()` also returns the *reason*, and
    the reason is the interesting part of this demo — it is how you prove that
    Avery was served by an individual target while Jordan was served by a rule.

    In production code you would normally call `variation()` and ignore the
    reason; requesting detail on every evaluation has a small cost.
    """
    detail = ldclient.get().variation_detail(
        config.FLAG_KEY,
        context,
        # The fallback value, used only if LaunchDarkly is unreachable or the
        # flag does not exist. Always the safe, already-released experience.
        config.FLAG_FALLBACK_VARIATION,
    )

    reason = detail.reason or {}
    kind = reason.get("kind", "UNKNOWN")

    return {
        "variation": str(detail.value),
        "variationIndex": detail.variation_index,
        "reasonKind": kind,
        "mechanism": _MECHANISM_BY_REASON.get(kind, "error"),
        "reasonText": describe_reason(reason, detail.is_default_value()),
        "ruleId": reason.get("ruleId"),
        "ruleIndex": reason.get("ruleIndex"),
        "inExperiment": bool(reason.get("inExperiment")),
        "isFallback": detail.is_default_value(),
    }


def describe_reason(reason: dict, is_default: bool) -> str:
    """Turn LaunchDarkly's evaluation reason into a sentence for the UI.

    The wording deliberately names the LaunchDarkly mechanism ("individual
    target", "targeting rule", "default rule") so that what you read in the app
    matches what you see in the LaunchDarkly Targeting tab.
    """
    kind = reason.get("kind", "UNKNOWN")

    if kind == "TARGET_MATCH":
        return (
            "INDIVIDUAL TARGETING — this visitor's key is listed directly on the "
            "flag. Individual targets are evaluated before any rule, so this "
            "wins even when a rule would have matched too."
        )
    if kind == "RULE_MATCH":
        rule = reason.get("ruleId") or "unnamed"
        index = reason.get("ruleIndex")
        position = f"rule #{index + 1}" if isinstance(index, int) else "a rule"
        return (
            f"RULE-BASED TARGETING — matched {position} (id {rule}). Everyone "
            "whose attributes satisfy this rule gets the same variation, with no "
            "code change and no deploy."
        )
    if kind == "FALLTHROUGH":
        if reason.get("inExperiment"):
            return (
                "DEFAULT RULE — this visitor was bucketed by a percentage "
                "rollout in the flag's default rule."
            )
        return (
            "DEFAULT RULE — no individual target and no targeting rule matched, "
            "so the flag's default rule applies. This is what almost all 40,000 "
            "daily visitors receive."
        )
    if kind == "OFF":
        return (
            "FLAG IS OFF — targeting is disabled, so every visitor gets the "
            "off variation. This is the instant, global kill switch."
        )
    if kind == "PREREQUISITE_FAILED":
        return f"A prerequisite flag ({reason.get('prerequisiteKey')}) is not satisfied."
    if kind == "ERROR":
        error_kind = reason.get("errorKind", "UNKNOWN")
        if error_kind == "FLAG_NOT_FOUND":
            return (
                f"Flag '{config.FLAG_KEY}' was not found in this environment — "
                "serving the safe fallback. Create the flag first (README, Step 4)."
            )
        if error_kind == "CLIENT_NOT_READY":
            return "The SDK is not connected yet — serving the safe fallback."
        return f"Evaluation error ({error_kind}) — serving the safe fallback."
    if is_default:
        return "Serving the code-level fallback value."
    return f"Served by LaunchDarkly ({kind})."


def all_flags_state(context: Context) -> dict:
    """Every flag value for this context, as LaunchDarkly currently sees it.

    Not needed for the demo's core loop; included because it is the call you
    would use to hand a whole set of flags to a front end in one round trip.
    """
    state = ldclient.get().all_flags_state(context)
    return state.to_values_map() if state.valid else {}


def track(event_key: str, context: Context, data: Optional[dict] = None, metric_value: Optional[float] = None) -> None:
    """Send a custom analytics event to LaunchDarkly.

    Custom events become metrics you can attach to the flag, so the landing page
    revamp can be judged on conversion rate per variation instead of opinion.
    """
    ldclient.get().track(event_key, context, data, metric_value)


# ---------------------------------------------------------------------------
# The listener — targeting changes with no page reload
# ---------------------------------------------------------------------------


def add_flag_value_change_listener(
    context: Context,
    callback: Callable[[str], None],
) -> Any:
    """Call `callback(new_variation)` when the flag's value changes for `context`.

    LaunchDarkly pushes the change down the streaming connection, the SDK
    re-evaluates the flag for this specific context, and — only if the resulting
    *value* actually changed for this person — invokes our callback on a
    background SDK thread.

    Because it is value-based and context-aware, adding one name to the flag's
    individual targets notifies only that person's session. Everyone else's
    browser stays untouched, which is exactly the blast-radius control the
    landing page project needs.

    Returns an opaque handle; pass it to `remove_flag_value_change_listener()`
    when the session ends so the SDK stops tracking a context nobody is viewing.
    """

    def _on_change(change: FlagValueChange) -> None:
        # `change` also carries `.key` and `.old_value` if you need them.
        callback(str(change.new_value))

    return ldclient.get().flag_tracker.add_flag_value_change_listener(
        config.FLAG_KEY, context, _on_change
    )


def remove_flag_value_change_listener(handle: Any) -> None:
    """Detach a listener created by `add_flag_value_change_listener()`."""
    ldclient.get().flag_tracker.remove_listener(handle)


# ---------------------------------------------------------------------------
# Offline demo support (OFFLINE_DEMO=1 only)
# ---------------------------------------------------------------------------

# The variation list, in the order the flag defines them. Index 0 is the
# control, which is also the off variation and the fallback.
VARIATIONS = ["control", "spotlight", "conversion"]

# The individual target and the rule the README asks you to build in the UI.
# Keeping them here lets the offline mode reproduce the finished configuration
# exactly, so the demo tells the same story with or without an account.
_OFFLINE_INDIVIDUAL_TARGET_KEY = "user-avery-chen"
_OFFLINE_RULE_ID = "beta-testers-on-paid-plans"


class _OfflineDataSource:
    """A stand-in for LaunchDarkly's streaming connection, for offline demos.

    Deliberately *not* the SDK's built-in `TestData` source. `TestData` writes
    straight to the feature store, bypassing the SDK's change-broadcasting
    layer, so flag change listeners never fire. This source writes through
    `config.data_source_update_sink` exactly as the real streaming processor
    does — so the offline demo exercises the same listener path, and the same
    targeting engine, as a live LaunchDarkly connection.

    The flag payload below is the real LaunchDarkly wire format. The SDK's own
    evaluator applies the individual target and the rule, which is why the
    offline mode reports honest TARGET_MATCH / RULE_MATCH / FALLTHROUGH reasons
    rather than faking them.

    The SDK instantiates this for us because it is passed as
    `Config(update_processor_class=...)`.
    """

    instance: "Optional[_OfflineDataSource]" = None

    def __init__(self, sdk_config: Config, store, ready):
        # The sink broadcasts flag changes; the raw store is only a fallback.
        self._sink = sdk_config.data_source_update_sink or store
        self._ready = ready
        self._version = 0
        self._targeting_on = True
        _OfflineDataSource.instance = self

    def start(self) -> None:
        from ldclient.versioned_data_kind import FEATURES

        self._sink.init({FEATURES: {config.FLAG_KEY: self._flag_data()}})
        self._ready.set()

    def stop(self) -> None:
        pass

    def initialized(self) -> bool:
        return True

    def set_targeting(self, on: bool) -> None:
        """Toggle the flag on/off, as the LaunchDarkly kill switch would."""
        from ldclient.versioned_data_kind import FEATURES

        self._targeting_on = on
        self._sink.upsert(FEATURES, self._flag_data())

    def is_targeting_on(self) -> bool:
        return self._targeting_on

    def _flag_data(self) -> dict:
        """The wire format LaunchDarkly sends for this flag, fully configured."""
        self._version += 1
        return {
            "key": config.FLAG_KEY,
            "version": self._version,
            "on": self._targeting_on,
            "variations": VARIATIONS,
            # --- individual targeting: matched before any rule --------------
            "targets": [
                {"variation": 2, "values": [_OFFLINE_INDIVIDUAL_TARGET_KEY]},
            ],
            "contextTargets": [],
            # --- rule-based targeting: betaTester AND plan in (ent, pro) ----
            "rules": [
                {
                    "id": _OFFLINE_RULE_ID,
                    "variation": 1,
                    "clauses": [
                        {
                            "contextKind": "user",
                            "attribute": "betaTester",
                            "op": "in",
                            "values": [True],
                            "negate": False,
                        },
                        {
                            "contextKind": "user",
                            "attribute": "plan",
                            "op": "in",
                            "values": ["enterprise", "pro"],
                            "negate": False,
                        },
                    ],
                    "trackEvents": False,
                }
            ],
            # --- everyone else ----------------------------------------------
            "fallthrough": {"variation": 0},
            "offVariation": 0,
            "prerequisites": [],
            "salt": "offline-demo",
            "deleted": False,
            "trackEvents": False,
            "clientSide": False,
        }


def _init_offline_demo() -> None:
    """Run with an in-process data source instead of LaunchDarkly."""
    ldclient.set_config(
        Config(
            "sdk-offline-demo",  # not a real key; never leaves the process
            update_processor_class=_OfflineDataSource,
            send_events=False,
        )
    )
    log.warning("OFFLINE_DEMO is on — not connected to LaunchDarkly.")


def offline_set_targeting(on: bool) -> None:
    """Toggle the in-memory flag. Only valid when OFFLINE_DEMO=1."""
    if _OfflineDataSource.instance is None:
        raise RuntimeError("Offline demo mode is not enabled (set OFFLINE_DEMO=1).")
    _OfflineDataSource.instance.set_targeting(on)


def offline_is_targeting_on() -> bool:
    if _OfflineDataSource.instance is None:
        return False
    return _OfflineDataSource.instance.is_targeting_on()
