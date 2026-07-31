# Ship faster without shipping risk — a LaunchDarkly demo for ABC Company

A small, complete Python application that demonstrates how feature flags let an
engineering team release faster **without** lowering the quality bar.

> **The problem.** Competitors are catching up. Leadership wants features out the
> door faster. Quality is a core value and cannot slip. So we need to (a) get new
> code onto production servers before it is exposed to customers, (b) expose it
> to a small, safe audience first, and (c) be able to take it back instantly if
> something is wrong — without a deploy, a rollback pipeline, or a page reload
> for the customers who are mid-session.
>
> **The answer this app demonstrates.** Deploy is decoupled from release. New
> code ships dark behind a flag, is enabled for internal staff in production,
> then widened. If it misbehaves, one flag change — from the UI, from `curl`, or
> from an alerting system — removes it from every user's screen in milliseconds.

Everything runs on your laptop against your own LaunchDarkly account. There is no
build step, no database, and no cloud infrastructure.

---

## Table of contents

1. [What you will see](#what-you-will-see)
2. [Assumptions about your environment](#assumptions-about-your-environment)
3. [Setup, step by step](#setup-step-by-step)
4. [The demo walkthrough](#the-demo-walkthrough)
5. [How it works](#how-it-works)
6. [Offline self-test (no LaunchDarkly account needed)](#offline-self-test-no-launchdarkly-account-needed)
7. [Troubleshooting](#troubleshooting)
8. [Notes for production use](#notes-for-production-use)

---

## What you will see

The app is a fictional "ABC Company Operations Cloud" dashboard. The feature
being released is **Order Insights v2** — a richer version of an existing panel.
Both versions are in the codebase at the same time; LaunchDarkly decides which
one each person gets.

| Requirement | How this app satisfies it |
| --- | --- |
| **Feature flag** | A single boolean flag, `release-order-insights-v2`, wraps the new panel. Toggling it on releases the feature; toggling it off rolls it back. |
| **Instant releases / rollbacks with no page reload** | The Python SDK holds a streaming connection to LaunchDarkly. A flag change fires a **flag value change listener** in the server, which pushes the newly rendered panel to every open browser tab over Server-Sent Events. The DOM swaps in place. No refresh, no redeploy, no restart. |
| **Test in production** | Three personas with different context attributes (`role`, `betaTester`, `plan`). A targeting rule releases the feature to internal QA only, then to beta customers, then to everyone — all while the same binary runs in production. |
| **Remediate** | A LaunchDarkly **flag trigger**: a URL that turns the flag off when it receives an HTTP POST. Fire it from `curl`, from the app's "Emergency rollback" button, or from any monitoring tool. A REST API fallback is included for plans without triggers. |

---

## Assumptions about your environment

This guide assumes all of the following. If any is not true, see
[Troubleshooting](#troubleshooting).

**Software**

- **Python 3.10 or newer** on your `PATH`. Check with `python3 --version`.
  (Developed and tested against Python 3.13.5 on Linux. 3.10 is the floor because
  the code uses `X | None` type syntax.)
- **`pip` and the `venv` module** available — both ship with python.org and most
  distro Python builds. On Debian/Ubuntu you may need `sudo apt install
  python3-venv`.
- **Git**, to clone the repository.
- **`curl`** and **`bash`**, for the command-line remediation step. On Windows,
  use WSL, Git Bash, or run the equivalent PowerShell shown inline.
- A **modern browser** (Chrome, Edge, Firefox, or Safari). The live-update
  mechanism uses `EventSource`, which every current browser supports.

**Network**

- Outbound HTTPS to `stream.launchdarkly.com`, `events.launchdarkly.com`, and
  `app.launchdarkly.com` (ports 443). A corporate proxy that blocks or buffers
  long-lived connections will break the streaming update — see
  [Troubleshooting](#troubleshooting).
- Nothing needs to reach *into* your machine. The app listens on `127.0.0.1` only.

**LaunchDarkly**

- A LaunchDarkly account — a free trial is enough for everything except the flag
  trigger in Step 7, which has a documented REST API alternative.
- Permission in that account to create a flag and read an SDK key.
- You will be working in a **non-production environment** (the "Test" environment
  that every new LaunchDarkly project ships with is ideal).

**What is deliberately not production-grade**

This is a demonstration, not a template to deploy. It uses Flask's development
server, keeps session state in process memory, and has no authentication. See
[Notes for production use](#notes-for-production-use).

---

## Setup, step by step

### Step 1 — Get the code

```bash
git clone https://github.com/mmccullough24/launchdarkly-safe-release-demo.git
cd launchdarkly-safe-release-demo
```

### Step 2 — Create a virtual environment

A virtual environment keeps these dependencies away from your system Python.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Your prompt should now be prefixed with `(.venv)`. Everything below assumes the
environment is active. To leave it later, run `deactivate`.

### Step 3 — Install the dependencies

```bash
pip install -r requirements.txt
```

This installs four packages: the LaunchDarkly server-side Python SDK, Flask,
`python-dotenv`, and `requests`. Nothing else is required.

> Using [uv](https://github.com/astral-sh/uv) instead? `uv venv && uv pip install -r requirements.txt`.

### Step 4 — Create the feature flag in LaunchDarkly

The app expects a flag to exist. **You must create it yourself** — flags cannot be
created by an SDK.

1. Sign in to [app.launchdarkly.com](https://app.launchdarkly.com).
2. Pick the project and environment you want to demo in (top-left project
   selector, and the environment selector beside it). The default project's
   **Test** environment is a good choice.
3. Go to **Flags** and click **Create flag**.
4. Fill in:
   - **Name:** `Release Order Insights v2`
   - **Key:** `release-order-insights-v2` — this must match exactly. The app
     reads it from `LD_FLAG_KEY` in your `.env`, which defaults to this value.
   - **Flag type / Configuration:** **Boolean** (variations `true` and `false`).
   - **Default variations:** serve `true` when targeting is **on**, `false` when
     targeting is **off**. This is the default for a new boolean flag — leave it.
   - **Client-side SDK availability:** you can leave every box unchecked. This
     app evaluates the flag server-side; the browser never contacts LaunchDarkly.
5. Click **Create flag**.
6. On the flag's page, confirm the toggle at the top is **off** for your
   environment. Starting from "off" is what lets you demonstrate the release.

### Step 5 — Copy your SDK key

1. In LaunchDarkly, open **Project settings → Environments**.
2. Find the environment you created the flag in.
3. Open its **⋯** (overflow) menu and choose **SDK key → Copy**.

The value starts with `sdk-`. If what you copied starts with `mob-` or is called
a "client-side ID", you have the wrong one — this app uses the **server-side**
SDK key.

> **Treat the SDK key as a secret.** It grants read access to every flag in that
> environment. `.env` is git-ignored so it cannot be committed by accident.

### Step 6 — Configure the app

```bash
cp .env.example .env
```

Open `.env` in an editor and paste your key:

```dotenv
LAUNCHDARKLY_SDK_KEY=sdk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

That is the only value you need to change to run the demo. Every other setting in
`.env.example` is optional and documented inline in that file.

### Step 7 — Wire up the kill switch (optional but recommended)

This enables the **Emergency rollback** button and `scripts/remediate.sh`. You can
skip it and toggle the flag in the LaunchDarkly UI instead; the rest of the demo
works either way.

**Option A — a flag trigger (preferred).**

1. Open the `release-order-insights-v2` flag.
2. Go to the flag's **Settings** tab (on some plans this lives behind the **⋯**
   menu) and find **Triggers**.
3. Click **Add trigger**.
4. Choose the integration **Generic trigger** and the action **Turn off flag**.
5. Save, then **copy the generated URL** — LaunchDarkly shows it once.
6. Put it in `.env`:

   ```dotenv
   LD_KILL_SWITCH_TRIGGER_URL=https://app.launchdarkly.com/webhook/triggers/...
   ```

   Anyone holding this URL can turn your flag off. Treat it like a password.

**Option B — the REST API (if triggers are not on your plan).**

1. Go to **Account settings → Authorization → Create token**.
2. Give it the built-in **Writer** role and copy the token (shown once).
3. Add to `.env`:

   ```dotenv
   LD_API_TOKEN=api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   LD_PROJECT_KEY=default
   LD_ENVIRONMENT_KEY=test
   ```

   `LD_PROJECT_KEY` and `LD_ENVIRONMENT_KEY` are the short URL keys, not the
   display names. Find them under **Project settings → Environments**.

Option B also unlocks `./scripts/remediate.sh --on` and `--status`, which is handy
when re-running the demo.

### Step 8 — Run it

```bash
python app.py
```

You should see:

```
==============================================================================
  ABC Company — Order Insights dashboard (LaunchDarkly demo)
==============================================================================
  SDK status      : connected to LaunchDarkly
  Feature flag    : release-order-insights-v2
  Remediation via : flag trigger URL
  Dashboard       : http://127.0.0.1:5000/
==============================================================================
```

Open <http://127.0.0.1:5000/> in your browser. The right-hand rail should show
**live (server-sent events)** under "Live connection". If it says
`reconnecting…`, jump to [Troubleshooting](#troubleshooting).

Leave the app running for the whole walkthrough.

---

## The demo walkthrough

Arrange your screen with the browser on one side and LaunchDarkly on the other,
so both are visible at once. **Do not reload the page at any point** — that is
the whole point.

### Part 1 — The safe default

The dashboard shows **Order Insights v1**: a plain table of recent orders. The
release-control rail reads `not released`, and the reason line explains why.

This is the code path that has been in production for months. Note that the *new*
code is already deployed — it is sitting in `features/order_insights.py` on the
running server, one boolean away from being visible. Deploy and release are
already separate.

### Part 2 — Release the feature (instant, no reload)

1. In LaunchDarkly, open `release-order-insights-v2`.
2. Flip the environment toggle to **on** and save (LaunchDarkly may ask you to
   confirm with a comment).
3. **Watch the browser.** Within a moment, without touching it:
   - the panel animates and becomes the v2 dashboard — stat tiles, a revenue
     trend chart, regional breakdown, and an "orders needing attention" table;
   - the pill flips to `released`;
   - a green line appears in the live event log.

Nothing was redeployed and nothing was refreshed. The Python process received the
change over its streaming connection, re-rendered the panel, and pushed it to the
open tab.

### Part 3 — Roll it back (instant)

Toggle the flag **off** in LaunchDarkly. The browser returns to v1 just as fast,
and a red line lands in the event log.

That round trip — release and rollback — is the risk reduction. The cost of
being wrong is now seconds, not a redeploy.

### Part 4 — Test in production, safely

Rather than releasing to everyone at once, release to people who can absorb a
bug. The persona switcher in the top-right changes who the flag is evaluated for.

1. Leave the flag **on** but restrict who it serves:
   - On the flag's **Targeting** tab, click **Add rule** (or "Add custom rule").
   - Build the rule: **if** `betaTester` **is one of** `true` **then serve**
     `true`.
   - Set the **Default rule** (the fallthrough, below your rules) to serve
     `false`.
   - Save.

   > The `betaTester` attribute appears in the rule builder once the SDK has
   > evaluated the flag for a context that carries it — that is, once you have
   > loaded the dashboard at least once. If it does not autocomplete, just type
   > the name; the rule works either way.

2. Back in the browser, click through the three personas. Each click re-opens the
   live stream for a different LaunchDarkly context:

   | Persona | Attributes | Sees |
   | --- | --- | --- |
   | **Avery Chen** — QA Engineer | `role: internal-qa`, `betaTester: true` | **v2** — matched the rule |
   | **Jordan Blake** — enterprise customer, early access | `betaTester: true` | **v2** — matched the rule |
   | **Riley Torres** — GA customer | `betaTester: false` | **v1** — fell through to the default rule |

   The reason line under the flag key updates to explain each outcome
   (`Matched a targeting rule…` vs `serving the default rule`).

3. To perform the full release, change the **Default rule** to serve `true`.
   Every open tab switches, live.

This is the whole "safe way to test in production": the new code runs on the same
production servers, against production data, exercised by real staff and opted-in
customers — with a blast radius you choose and can shrink at any moment.

### Part 5 — Remediate: kill the feature from outside the UI

A bug slipped through. Someone needs it gone *now*, and they may not have a
LaunchDarkly login open.

1. First, make sure the feature is visible again (flag on, default rule serving
   `true`), and pick a persona who can see v2.
2. Optional: click **Report a problem**. That sends a custom metric event
   (`order-insights-issue-reported`) to LaunchDarkly. Attach that metric to the
   flag and you can watch error rates per variation while a release is in flight
   — the signal that turns "I have a bad feeling" into a decision.
3. Now fire the kill switch. Any of these does the same thing:

   **From a terminal:**

   ```bash
   ./scripts/remediate.sh
   ```

   **Raw `curl`** (what the script runs — this is the "one line in a runbook"
   version):

   ```bash
   curl -X POST "https://app.launchdarkly.com/webhook/triggers/YOUR-TRIGGER-URL"
   ```

   **From the browser:** click **Emergency rollback** in the right-hand rail.

   **PowerShell, if you are on Windows:**

   ```powershell
   Invoke-RestMethod -Method Post -Uri "https://app.launchdarkly.com/webhook/triggers/YOUR-TRIGGER-URL"
   ```

4. Watch every open tab drop back to v1 at once. Check the flag in LaunchDarkly:
   it is off, with an audit-log entry recording that the trigger fired.

Because the trigger is just an HTTP POST, the realistic version of this is
automated: wire it to a Datadog monitor, a PagerDuty incident action, a Slack
workflow, or a synthetic check, so a spike in errors turns the feature off before
a human reads the alert.

To reset for another run: `./scripts/remediate.sh --on` (needs `LD_API_TOKEN`), or
toggle the flag on in the UI.

---

## How it works

### The flow, end to end

```
   You toggle the flag
   in LaunchDarkly
          │
          ▼
   ┌──────────────────┐   streaming connection (held open by the SDK)
   │   LaunchDarkly   │ ─────────────────────────────────┐
   └──────────────────┘                                  │
                                                         ▼
                                        ┌────────────────────────────────┐
                                        │  Python process (app.py)       │
                                        │                                │
                                        │  LDClient                      │
                                        │    └─ flag_tracker             │
                                        │         add_flag_value_change_ │
                                        │         listener(flag, ctx, cb)│
                                        │            │                   │
                                        │            ▼                   │
                                        │  SessionHub → per-tab queue    │
                                        │            │                   │
                                        │            ▼                   │
                                        │  /api/stream (Server-Sent      │
                                        │   Events), one per open tab    │
                                        └────────────┬───────────────────┘
                                                     │  event: state
                                                     ▼
                                        ┌────────────────────────────────┐
                                        │  Browser (static/js/app.js)    │
                                        │  swaps #feature-panel in place │
                                        └────────────────────────────────┘
```

Two separate "push" hops, and neither is a poll:

1. **LaunchDarkly → server.** The SDK's default streaming data source keeps a
   connection open. Flag changes arrive in milliseconds. This is what
   `ld_integration.add_flag_value_change_listener()` hooks into — it is
   *value*-based and *context*-aware, so a session is only notified when the
   value for **that person** changes.
2. **Server → browser.** Each open tab holds a Server-Sent Events connection.
   When a listener fires, the server re-renders the panel and pushes the HTML
   down that tab's stream.

The browser never talks to LaunchDarkly and never sees the SDK key.

### File map

| File | What it does |
| --- | --- |
| `app.py` | Flask routes, the SSE endpoint, and startup/shutdown. Start here. |
| `ld_integration.py` | Every LaunchDarkly SDK call: init, evaluate, listener, custom events. |
| `personas.py` | The three demo users and the LaunchDarkly `Context` built for each. Targetable attributes are defined here. |
| `session_hub.py` | Tracks open browser tabs; registers and tears down one flag listener per tab. |
| `features/order_insights.py` | The feature itself — both the old and the new implementation, side by side. Knows nothing about LaunchDarkly. |
| `templates/panels/*.html` | The two rendered versions of the panel. |
| `remediation.py` | Fires the kill switch via trigger URL or REST API. |
| `scripts/remediate.sh` | The same kill switch from a terminal. |
| `config.py` | Reads `.env`. Every setting is documented in place. |

### The pattern worth copying

The flag check happens at **one place, at the edge** (`app.py`), and the result is
handed to the feature code as a plain boolean:

```python
flag_on = ld_integration.evaluate(context)["value"]
view = order_insights.build_view(flag_on)
```

`features/order_insights.py` never imports the SDK. That keeps the feature
testable without a LaunchDarkly connection, and when the release is finished you
delete one branch and the flag rather than unpicking SDK calls scattered through
the codebase.

The fallback value is also deliberate. `ld_integration.evaluate()` passes
`FLAG_FALLBACK_VALUE = False`, so if LaunchDarkly is unreachable, the key is bad,
or the flag does not exist, every customer gets the known-good v1. **The
fail-safe direction is always "the thing that already worked."**

---

## Offline self-test (no LaunchDarkly account needed)

To verify your Python setup before you have credentials — or to see the UI on a
plane — run:

```bash
OFFLINE_SELF_TEST=1 python app.py
```

The app serves the flag from an in-process data source instead of LaunchDarkly,
and the page grows two buttons that toggle it. A warning banner makes the mode
obvious.

This is a faithful test of the listener path, not a mock of it: the in-process
source writes through the same change-broadcasting layer the real streaming
connection uses, so the same `flag_tracker` listener fires and the same SSE
message reaches the browser. Only the transport differs.

---

## Troubleshooting

**`*** LaunchDarkly did not initialize.`**
The SDK could not fetch flags within its startup window. In order of likelihood:
the key in `.env` is a client-side ID or mobile key rather than an `sdk-` key;
the key was copied with a trailing space; or outbound HTTPS to
`stream.launchdarkly.com` is blocked. Test the last one with
`curl -sSf -o /dev/null https://app.launchdarkly.com` .

**The page loads but "Live connection" says `reconnecting…`.**
Something between the browser and the app is buffering. If you put the app behind
nginx, set `proxy_buffering off` for `/api/stream`. Otherwise check for a
corporate proxy or a browser extension that terminates long-lived requests.

**Toggling the flag changes nothing in the browser.**
Work down this list:
1. Is the flag key in LaunchDarkly exactly `release-order-insights-v2`? A
   mismatch shows up in the reason line as *"was not found in this
   environment"*.
2. Did you toggle the flag in the **same environment** as the SDK key you
   configured? This is the most common cause — the environment selector in the
   LaunchDarkly UI is independent of which key you copied.
3. Is the currently selected persona actually affected by the change? A targeting
   rule that only serves beta testers will not notify Riley Torres — that is
   correct behaviour, and the point of Part 4.
4. Check the terminal running `app.py`. Every listener firing logs a line like
   `Flag 'release-order-insights-v2' changed to True for avery`.

**`Address already in use` on startup.**
Something else owns port 5000 — on macOS, usually AirPlay Receiver. Either turn
that off in **System Settings → General → AirDrop & Handoff**, or run on another
port: `PORT=5050 python app.py`.

**`./scripts/remediate.sh: Permission denied`.**
`chmod +x scripts/remediate.sh`, or run it as `bash scripts/remediate.sh`.

**The kill switch returns HTTP 404 or 401.**
For a trigger URL: it was mistyped, or the trigger was deleted in LaunchDarkly.
For the REST API: check `LD_PROJECT_KEY` and `LD_ENVIRONMENT_KEY` are the short
keys (e.g. `default` / `test`) and that the token has write access.

**`ModuleNotFoundError: No module named 'ldclient'`.**
The virtual environment is not active. Re-run the activate command from Step 2 —
your prompt should show `(.venv)`.

---

## Notes for production use

What this demo does that a real deployment should do differently:

- **Web server.** Flask's development server is single-process and not hardened.
  Use gunicorn/uvicorn behind a real proxy — and note that each worker process
  gets its own SDK client, which is fine and expected.
- **Session state.** `SessionHub` is in-process memory, so it does not survive a
  restart and does not span workers. With multiple workers, each holds its own
  listeners and pushes to its own connected tabs, which still works; a shared bus
  (Redis pub/sub) is only needed if you want cross-process fan-out.
- **One client, forever.** The SDK client is created once at startup and reused.
  Creating one per request would open a streaming connection per request.
- **Secrets.** The SDK key belongs in your secret manager, not a `.env` file on
  disk.
- **Flag lifecycle.** A release flag is temporary. Once v2 is at 100% and stable,
  delete the `legacy_view()` branch and archive the flag. LaunchDarkly's code
  references and flag status views exist to stop temporary flags becoming
  permanent debt.
- **Metrics.** The `order-insights-issue-reported` event is illustrative. In a
  real rollout you would attach real metrics to the flag and use guarded releases
  to automate the rollback this demo triggers by hand.

---

## License

MIT — see [LICENSE](LICENSE).
