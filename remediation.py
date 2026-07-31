"""Remediation: turning the flag off from outside the LaunchDarkly UI.

When a bug slips through, you want the fastest possible path to "customers are
safe again" — ideally one that an on-call engineer, a runbook, or an automated
alert can take without logging in to a dashboard.

Two mechanisms are supported, in order of preference:

1. **Flag trigger** (`LD_KILL_SWITCH_TRIGGER_URL`) — a LaunchDarkly-generated
   webhook URL bound to a single action, "turn off flag". Anything that can send
   an HTTP POST can fire it: curl, a browser button, PagerDuty, Datadog, a
   Slack workflow. No credentials to distribute beyond the URL itself.

2. **REST API** (`LD_API_TOKEN`) — a semantic-patch call against the flag. Use
   this if flag triggers are not on your LaunchDarkly plan. It can also turn the
   flag back *on*, which a trigger bound to "turn off" cannot.

Both do the same thing a human clicking the flag's toggle would do, so the
change streams out to every connected SDK immediately.
"""

import logging

import requests

import config

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10

# LaunchDarkly's "semantic patch" content type. It lets you describe the change
# you want ("turn this flag off") instead of a JSON Patch document, so it is
# safe against concurrent edits by other people.
_SEMANTIC_PATCH_CONTENT_TYPE = "application/json; domain-model=launchdarkly.semanticpatch"


def is_configured() -> bool:
    """True if any remediation path is available."""
    return bool(config.KILL_SWITCH_TRIGGER_URL or config.LD_API_TOKEN)


def describe_configuration() -> str:
    if config.KILL_SWITCH_TRIGGER_URL:
        return "flag trigger URL"
    if config.LD_API_TOKEN:
        return "LaunchDarkly REST API"
    return "not configured"


def kill_switch() -> tuple[bool, str]:
    """Turn the release flag OFF. Returns (succeeded, message-for-the-user)."""
    if config.KILL_SWITCH_TRIGGER_URL:
        return _fire_trigger(config.KILL_SWITCH_TRIGGER_URL)
    if config.LD_API_TOKEN:
        return _set_flag_via_api(turn_on=False)
    return False, (
        "No remediation path configured. Set LD_KILL_SWITCH_TRIGGER_URL "
        "(preferred) or LD_API_TOKEN in your .env — see the README."
    )


def restore() -> tuple[bool, str]:
    """Turn the release flag back ON. Requires the REST API path.

    A generic trigger is bound to one action when you create it, so a
    "turn off flag" trigger cannot turn it back on. Re-releasing is a deliberate
    act anyway — do it from the LaunchDarkly UI or with an API token.
    """
    if config.LD_API_TOKEN:
        return _set_flag_via_api(turn_on=True)
    return False, (
        "Turning the flag back on needs LD_API_TOKEN (a trigger can only perform "
        "the single action it was created with). Use the LaunchDarkly UI instead."
    )


def _fire_trigger(url: str) -> tuple[bool, str]:
    """POST to a LaunchDarkly flag trigger URL."""
    try:
        response = requests.post(url, timeout=_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # Deliberately does not log the URL: a trigger URL is a credential.
        log.error("Trigger request failed: %s", type(exc).__name__)
        return False, f"Could not reach LaunchDarkly: {type(exc).__name__}"

    if response.ok:
        return True, "Trigger fired — LaunchDarkly is turning the flag off."
    return False, f"Trigger returned HTTP {response.status_code}: {response.text[:200]}"


def _set_flag_via_api(turn_on: bool) -> tuple[bool, str]:
    """Turn the flag on or off with a semantic-patch REST call."""
    url = f"{config.LD_API_BASE_URL}/api/v2/flags/{config.LD_PROJECT_KEY}/{config.FLAG_KEY}"
    instruction = "turnFlagOn" if turn_on else "turnFlagOff"
    body = {
        "environmentKey": config.LD_ENVIRONMENT_KEY,
        "instructions": [{"kind": instruction}],
        "comment": "Fired from the ABC Company release-safety demo app.",
    }

    try:
        response = requests.patch(
            url,
            json=body,
            headers={
                "Authorization": config.LD_API_TOKEN,
                "Content-Type": _SEMANTIC_PATCH_CONTENT_TYPE,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.error("LaunchDarkly API request failed: %s", type(exc).__name__)
        return False, f"Could not reach the LaunchDarkly API: {type(exc).__name__}"

    if response.ok:
        state = "on" if turn_on else "off"
        return True, f"LaunchDarkly API accepted the change — flag is now {state}."
    # Response bodies from the API describe the problem (bad token, wrong
    # project/environment key) and do not contain the token itself.
    return False, f"LaunchDarkly API returned HTTP {response.status_code}: {response.text[:200]}"
