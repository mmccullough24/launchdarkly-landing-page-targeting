"""Everything this app does with the LaunchDarkly Python SDK.

Three things matter here, and they map directly onto the three requirements of
the demo:

1. `initialize()`   — one long-lived, process-wide SDK client. It holds a
                      streaming connection to LaunchDarkly, so flag changes
                      arrive in milliseconds instead of being polled for.
2. `evaluate()`     — ask LaunchDarkly what a specific person should see right
                      now. This is the flag check that wraps the new feature.
3. `add_flag_value_change_listener()` — the "listener". LaunchDarkly calls us
                      when the flag's value changes for a given context, which
                      is how the browser can switch code paths with no reload.
"""

import logging
from typing import Any, Callable, Optional

import ldclient
from ldclient import Context
from ldclient.config import Config
from ldclient.interfaces import FlagValueChange

import config

log = logging.getLogger(__name__)

# Keeps the SDK's own (fairly chatty) logging out of the demo output. Drop this
# to logging.DEBUG if you need to see the streaming connection handshake.
logging.getLogger("ldclient").setLevel(logging.WARNING)



# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def initialize() -> bool:
    """Start the shared LaunchDarkly client. Returns True if it connected.

    `ldclient.set_config()` creates a singleton client and blocks for up to five
    seconds while it downloads the initial flag payload. Create it once per
    process and share it — never one client per request.
    """
    if config.OFFLINE_SELF_TEST:
        _init_offline_self_test()
    else:
        if not config.SDK_KEY:
            log.error("LAUNCHDARKLY_SDK_KEY is not set — see .env.example")
            return False
        # A default Config streams flag updates over a persistent connection.
        # That streaming connection is what makes the rollback in this demo feel
        # instant; nothing here is polling on a timer.
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


def evaluate(context: Context) -> dict:
    """Evaluate the release flag for one person.

    Uses `variation_detail` rather than plain `variation` so the UI can show
    *why* LaunchDarkly served this value — which is the interesting part when
    you are demonstrating a targeted rollout.
    """
    detail = ldclient.get().variation_detail(
        config.FLAG_KEY,
        context,
        # Fallback value, used only if LaunchDarkly is unreachable or the flag
        # does not exist. Always the safe, already-released behaviour.
        config.FLAG_FALLBACK_VALUE,
    )

    reason = detail.reason or {}
    return {
        "value": bool(detail.value),
        "reasonKind": reason.get("kind", "UNKNOWN"),
        "reasonText": describe_reason(reason, detail.is_default_value()),
        "isFallback": detail.is_default_value(),
    }


def describe_reason(reason: dict, is_default: bool) -> str:
    """Turn LaunchDarkly's evaluation reason into a sentence for the UI."""
    kind = reason.get("kind", "UNKNOWN")

    if kind == "OFF":
        return "Flag is toggled OFF — serving the off variation to everyone."
    if kind == "TARGET_MATCH":
        return "This individual is targeted directly on the flag."
    if kind == "RULE_MATCH":
        rule = reason.get("ruleId") or f"index {reason.get('ruleIndex')}"
        return f"Matched a targeting rule ({rule}) — a subset of users, not everyone."
    if kind == "FALLTHROUGH":
        if reason.get("inExperiment"):
            return "Part of an experiment's default rollout."
        return "Flag is ON and this user matched no rule — serving the default rule."
    if kind == "PREREQUISITE_FAILED":
        return f"A prerequisite flag ({reason.get('prerequisiteKey')}) is not satisfied."
    if kind == "ERROR":
        error_kind = reason.get("errorKind", "UNKNOWN")
        if error_kind == "FLAG_NOT_FOUND":
            return (
                f"Flag '{config.FLAG_KEY}' was not found in this environment — "
                "serving the safe fallback. Create the flag (see README)."
            )
        return f"Evaluation error ({error_kind}) — serving the safe fallback."
    if is_default:
        return "Serving the code-level fallback value."
    return f"Served by LaunchDarkly ({kind})."


def track(event_key: str, context: Context, data: Optional[dict] = None) -> None:
    """Send a custom analytics event to LaunchDarkly.

    Custom events become metrics you can attach to the flag, so a release can be
    judged on real signal (error rates, conversions) rather than a hunch.
    """
    ldclient.get().track(event_key, context, data)


# ---------------------------------------------------------------------------
# The listener — instant releases and rollbacks
# ---------------------------------------------------------------------------


def add_flag_value_change_listener(
    context: Context,
    callback: Callable[[bool], None],
) -> Any:
    """Call `callback(new_value)` whenever the flag's value changes for `context`.

    This is the heart of the "no page reload" requirement. LaunchDarkly pushes
    the change down the streaming connection, the SDK re-evaluates the flag for
    this specific context, and — only if the resulting *value* actually changed
    for this person — invokes our callback on a background SDK thread.

    Because it is value-based and context-aware, flipping a targeting rule that
    only affects beta testers notifies the beta testers' sessions and leaves
    everyone else's alone.

    Returns an opaque handle; pass it to `remove_flag_value_change_listener()`
    when the session ends so the SDK stops tracking a context nobody is viewing.
    """

    def _on_change(change: FlagValueChange) -> None:
        # `change` also carries `.key` and `.old_value` if you need them.
        callback(bool(change.new_value))

    return ldclient.get().flag_tracker.add_flag_value_change_listener(
        config.FLAG_KEY, context, _on_change
    )


def remove_flag_value_change_listener(handle: Any) -> None:
    """Detach a listener created by `add_flag_value_change_listener()`."""
    ldclient.get().flag_tracker.remove_listener(handle)


# ---------------------------------------------------------------------------
# Offline self-test support (OFFLINE_SELF_TEST=1 only)
# ---------------------------------------------------------------------------


class _SelfTestDataSource:
    """A stand-in for LaunchDarkly's streaming connection, for offline testing.

    Deliberately *not* the SDK's built-in `TestData` source: `TestData` writes
    straight to the feature store, which bypasses the SDK's change-broadcasting
    layer, so flag change listeners never fire. This source writes through
    `config.data_source_update_sink` exactly as the real streaming processor
    does, so the offline self-test exercises the same listener path as a live
    LaunchDarkly toggle.

    The SDK instantiates this for us because it is passed as
    `Config(update_processor_class=...)`.
    """

    instance: "Optional[_SelfTestDataSource]" = None

    def __init__(self, sdk_config: Config, store, ready):
        # The sink broadcasts flag changes; the raw store is only a fallback.
        self._sink = sdk_config.data_source_update_sink or store
        self._ready = ready
        self._version = 0
        _SelfTestDataSource.instance = self

    def start(self) -> None:
        from ldclient.versioned_data_kind import FEATURES

        self._sink.init({FEATURES: {config.FLAG_KEY: self._flag_data(False)}})
        self._ready.set()

    def stop(self) -> None:
        pass

    def initialized(self) -> bool:
        return True

    def set(self, value: bool) -> None:
        from ldclient.versioned_data_kind import FEATURES

        self._sink.upsert(FEATURES, self._flag_data(value))

    def _flag_data(self, value: bool) -> dict:
        """The wire format LaunchDarkly would send for a simple boolean flag."""
        self._version += 1
        return {
            "key": config.FLAG_KEY,
            "version": self._version,
            "on": True,
            "variations": [True, False],
            "fallthrough": {"variation": 0 if value else 1},
            "offVariation": 1,
            "targets": [],
            "rules": [],
            "prerequisites": [],
            "salt": "self-test",
            "deleted": False,
            "trackEvents": False,
            "clientSide": False,
        }


def _init_offline_self_test() -> None:
    """Run with an in-process data source instead of LaunchDarkly."""
    ldclient.set_config(
        Config(
            "sdk-offline-self-test",  # not a real key; never leaves the process
            update_processor_class=_SelfTestDataSource,
            send_events=False,
        )
    )
    log.warning("OFFLINE_SELF_TEST is on — not connected to LaunchDarkly.")


def self_test_set_flag(value: bool) -> None:
    """Toggle the in-memory flag. Only valid when OFFLINE_SELF_TEST=1."""
    if _SelfTestDataSource.instance is None:
        raise RuntimeError("Offline self-test is not enabled (set OFFLINE_SELF_TEST=1).")
    _SelfTestDataSource.instance.set(value)
