"""Environment configuration for the ABC Company landing page targeting demo.

Every value is read from an environment variable, loaded from a local `.env`
file (see `.env.example`). Nothing in this repository should ever contain a real
credential — `.env` is git-ignored for exactly that reason.
"""

import os

from dotenv import load_dotenv

# Reads `.env` from the project root if it exists. Real environment variables
# always win over `.env` values, so any setting can be overridden inline:
#   LD_FLAG_KEY=my-other-flag python app.py
load_dotenv()


def _flag(name: str, default: str = "false") -> bool:
    """Read a boolean-ish environment variable."""
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# LaunchDarkly connection
# ---------------------------------------------------------------------------

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ REPLACE ME — put your own server-side SDK key in `.env`:                │
# │                                                                         │
# │     LAUNCHDARKLY_SDK_KEY=sdk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx       │
# │                                                                         │
# │ Find it in LaunchDarkly under:                                          │
# │     Project settings -> Environments -> the "..." menu on your          │
# │     environment -> SDK key -> Copy                                      │
# │                                                                         │
# │ It MUST start with `sdk-`. A mobile key (`mob-`) or a client-side ID    │
# │ will not work: this demo uses the server-side Python SDK, which         │
# │ evaluates flags on the server and never exposes the key to the browser. │
# └─────────────────────────────────────────────────────────────────────────┘
SDK_KEY = os.environ.get("LAUNCHDARKLY_SDK_KEY", "").strip()

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ RE-CREATE ME — you must create this flag yourself in LaunchDarkly.      │
# │ SDKs can read flags but cannot create them.                             │
# │                                                                         │
# │ Create a *string* flag with this exact key and three variations:        │
# │     control     — the hero currently in production                      │
# │     spotlight   — the redesign, for a targeted audience                 │
# │     conversion  — the boldest test, for named individuals               │
# │                                                                         │
# │ Full click-by-click steps are in README.md -> "Step 4".                 │
# │ To use a different key, set LD_FLAG_KEY in `.env` rather than editing   │
# │ this file.                                                              │
# └─────────────────────────────────────────────────────────────────────────┘
FLAG_KEY = os.environ.get("LD_FLAG_KEY", "landing-page-hero").strip()

# The variation served when LaunchDarkly cannot be reached at all: a bad SDK
# key, no network, or a LaunchDarkly outage. It is deliberately the control
# hero — the fail-safe direction is always the experience already in production.
# Never make this the new variation; an outage would then release the redesign
# to all 40,000 daily visitors at once.
FLAG_FALLBACK_VARIATION = "control"


# ---------------------------------------------------------------------------
# Optional: LaunchDarkly REST API access
# ---------------------------------------------------------------------------
# Only needed for `scripts/setup_launchdarkly.py`, which can create the flag and
# its targeting rules for you instead of clicking through the UI, and for the
# "reset targeting" button. The demo runs fine without any of this.
#
# Create a token under: Account settings -> Authorization -> Create token,
# with the built-in "Writer" role.
LD_API_TOKEN = os.environ.get("LD_API_TOKEN", "").strip()

# The project and environment *keys* — the short URL-safe ones, not the display
# names. Find them under Project settings -> Environments.
LD_PROJECT_KEY = os.environ.get("LD_PROJECT_KEY", "default").strip()
LD_ENVIRONMENT_KEY = os.environ.get("LD_ENVIRONMENT_KEY", "test").strip()

# Only change this if you are on a LaunchDarkly federal or dedicated instance.
LD_API_BASE_URL = os.environ.get("LD_API_BASE_URL", "https://app.launchdarkly.com").strip()


# ---------------------------------------------------------------------------
# Local web server settings
# ---------------------------------------------------------------------------

HOST = os.environ.get("HOST", "127.0.0.1").strip()
PORT = int(os.environ.get("PORT", "5000"))

# Offline demo mode. When enabled the app serves the flag from an in-process
# data source that mimics LaunchDarkly's targeting engine — individual targets
# and rules included — so you can see the whole demo with no account and no
# network. See README.md -> "Offline demo mode".
OFFLINE_DEMO = _flag("OFFLINE_DEMO")
