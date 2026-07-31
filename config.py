"""Environment configuration for the ABC Company release-safety demo.

Everything the app needs to talk to LaunchDarkly is read from environment
variables, which are loaded from a local `.env` file (see `.env.example`).
Nothing in this repository should ever contain a real credential.
"""

import os

from dotenv import load_dotenv

# Reads `.env` from the project root if it exists. Real environment variables
# always win over `.env` values, so you can override any setting inline, e.g.
#   LD_FLAG_KEY=my-other-flag python app.py
load_dotenv()


def _flag(name: str, default: str = "false") -> bool:
    """Read a boolean-ish environment variable."""
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# LaunchDarkly connection
# ---------------------------------------------------------------------------

# REPLACE ME: put your own server-side SDK key in `.env` as
# LAUNCHDARKLY_SDK_KEY=sdk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# Find it in LaunchDarkly under: Project settings -> Environments -> "..." menu
# on the environment you want -> SDK key.
# NOTE: this must be an *SDK key* (starts with `sdk-`), not a mobile key or a
# client-side ID — this demo uses the server-side Python SDK.
SDK_KEY = os.environ.get("LAUNCHDARKLY_SDK_KEY", "").strip()

# RE-CREATE ME: the feature flag this demo toggles. You must create a flag with
# this exact key in your LaunchDarkly project (see README, "Create the feature
# flag"). If you prefer a different key, set LD_FLAG_KEY in `.env` instead of
# editing this file.
FLAG_KEY = os.environ.get("LD_FLAG_KEY", "release-order-insights-v2").strip()

# The value served to every customer when LaunchDarkly cannot be reached at all
# (bad SDK key, no network, LaunchDarkly outage). It is deliberately `False`:
# the fallback is always the known-good, already-shipped experience.
FLAG_FALLBACK_VALUE = False


# ---------------------------------------------------------------------------
# Remediation ("kill switch") — see remediation.py and scripts/remediate.sh
# ---------------------------------------------------------------------------

# Option A (preferred): a LaunchDarkly flag trigger URL. Create it in the flag's
# Settings -> Triggers tab, choose "Generic trigger", action "Turn off flag",
# then paste the generated URL into `.env` as LD_KILL_SWITCH_TRIGGER_URL.
# The URL itself is the credential — treat it like a password.
KILL_SWITCH_TRIGGER_URL = os.environ.get("LD_KILL_SWITCH_TRIGGER_URL", "").strip()

# Option B (fallback): the LaunchDarkly REST API. Use this if flag triggers are
# not available on your plan. Create an access token under
# Account settings -> Authorization -> Create token (writer role or better).
LD_API_TOKEN = os.environ.get("LD_API_TOKEN", "").strip()
LD_PROJECT_KEY = os.environ.get("LD_PROJECT_KEY", "default").strip()
LD_ENVIRONMENT_KEY = os.environ.get("LD_ENVIRONMENT_KEY", "test").strip()
LD_API_BASE_URL = os.environ.get("LD_API_BASE_URL", "https://app.launchdarkly.com").strip()


# ---------------------------------------------------------------------------
# Local app settings
# ---------------------------------------------------------------------------

HOST = os.environ.get("HOST", "127.0.0.1").strip()
PORT = int(os.environ.get("PORT", "5000"))

# Optional offline smoke test. When enabled, the app swaps LaunchDarkly's
# streaming data source for the SDK's built-in TestData source so you can
# verify the whole pipeline (flag change -> SDK listener -> browser update)
# without a LaunchDarkly account. See README, "Offline self-test".
# This is a development aid only — the real demo runs with it off.
OFFLINE_SELF_TEST = _flag("OFFLINE_SELF_TEST")
