# Targeting the landing page revamp — a LaunchDarkly demo for ABC Company

A small, complete Python application that demonstrates **individual targeting**
and **rule-based targeting** with LaunchDarkly, on the component ABC Company
cares most about right now: the landing page hero.

> **The situation.** ABC Company is revamping its landing page. The project spans
> several teams; this team owns the hero — the first thing every visitor sees.
> The page takes about **40,000 visitors a day**, so a bad hero is not a small
> mistake. There are a lot of eyes on this project, and the bar for shipping is
> high.
>
> **The problem with "just ship it".** A landing page change is all-or-nothing:
> it either goes live for all 40,000 people or none of them. Testing on staging
> tells you it renders; it does not tell you whether it works on real traffic.
>
> **What this app shows.** One flag, three heroes, and two ways to decide who
> gets which. Named individuals can be pinned to a variation so the team sees the
> new hero in production before anyone else. Whole audiences can be described by
> their attributes — "beta testers on paid plans" — and served a variation by
> rule. Everyone else keeps the control. Changing any of it takes seconds, needs
> no deploy, and does not reload anyone's page.

Everything runs on your laptop against your own LaunchDarkly account. There is no
build step, no database, and no cloud infrastructure. If you do not have an
account yet, there is a fully working
[offline mode](#offline-demo-mode-no-launchdarkly-account-needed).

---

## Table of contents

1. [What this demonstrates](#what-this-demonstrates)
2. [What you will see](#what-you-will-see)
3. [Assumptions about your environment](#assumptions-about-your-environment)
4. [Setup, step by step](#setup-step-by-step)
5. [The demo walkthrough](#the-demo-walkthrough)
6. [How it works](#how-it-works)
7. [Offline demo mode (no LaunchDarkly account needed)](#offline-demo-mode-no-launchdarkly-account-needed)
8. [Troubleshooting](#troubleshooting)
9. [Notes for production use](#notes-for-production-use)

---

## What this demonstrates

| Requirement | How this app satisfies it |
| --- | --- |
| **Feature flag around a component** | The landing page hero is wrapped in a single string flag, `landing-page-hero`, with three variations: `control`, `spotlight`, `conversion`. All three heroes are in the codebase at once; LaunchDarkly decides which one each visitor gets. |
| **Evaluation context with user attributes** | Every evaluation sends a LaunchDarkly context carrying `role`, `plan`, `betaTester`, `region`, `accountAgeDays`, and `deviceType`. These are defined in `contexts.py` and are exactly what the targeting rules are built on. |
| **Individual targeting** | One named user — `user-avery-chen` — is pinned by key to the `conversion` variation, regardless of attributes. Individual targets are evaluated *before* any rule, so pinning someone overrides whatever a rule would have served them. |
| **Rule-based targeting** | A rule serves `spotlight` to everyone where `betaTester is true` **AND** `plan is one of (enterprise, pro)`. One rule, an entire audience, no code change. |
| **Everyone else** | The default rule serves `control` — what almost all 40,000 daily visitors receive. |

A three-variation flag is used rather than a boolean on purpose: it makes the two
targeting mechanisms *visually distinct*. When the individual target and the rule
serve different heroes, you can see which mechanism won instead of inferring it.

---

## What you will see

The app is the ABC Company landing page with a **targeting inspector** docked to
the right. The inspector is demo scaffolding, not part of the page: for the
current visitor it shows the variation served, the LaunchDarkly evaluation
reason, and the context attributes that produced it — colour-coded by mechanism.

Five visitors ship with the demo. Between them they cover every targeting path:

| Preview as | Attributes | Gets | Because |
| --- | --- | --- | --- |
| **Avery Chen** | `role: internal-qa`, `plan: internal`, `betaTester: true` | `conversion` | **Individual target** — listed by key on the flag |
| **Jordan Blake** | `plan: enterprise`, `betaTester: true` | `spotlight` | **Targeting rule** — matches both clauses |
| **Priya Raman** | `plan: pro`, `betaTester: true` | `spotlight` | **The same rule** — one rule, many people |
| **Sam Okafor** | `plan: enterprise`, `betaTester: false` | `control` | **Default rule** — enterprise, but not a beta tester, and the rule requires both |
| **Riley Torres** | `plan: free`, `betaTester: false` | `control` | **Default rule** — a typical visitor |

Sam Okafor is there deliberately: that visitor proves the rule's `AND` semantics.
Being on the enterprise plan is not enough on its own.

Switching visitors, or changing targeting in LaunchDarkly, updates the page
**with no reload** — the hero is swapped in place over a Server-Sent Events
stream. Details in [How it works](#how-it-works).

---

## Assumptions about your environment

This guide assumes all of the following. If any is not true, see
[Troubleshooting](#troubleshooting).

**Software**

- **Python 3.10 or newer** on your `PATH`. Check with `python3 --version`.
  (Developed and tested against Python 3.13.5 on Linux. 3.10 is the floor
  because the code uses the `X | None` type syntax.)
- **`pip` and the `venv` module** — both ship with python.org builds and most
  distro Python packages. On Debian/Ubuntu you may need
  `sudo apt install python3-venv`.
- **Git**, to clone the repository.
- A **modern browser** — Chrome, Edge, Firefox, or Safari. The live-update
  mechanism uses `EventSource`, which every current browser supports.
- Optional: **`curl`**, if you want to poke the JSON endpoints by hand.

**Network**

- Outbound HTTPS on port 443 to `stream.launchdarkly.com`,
  `events.launchdarkly.com`, and `app.launchdarkly.com`. A corporate proxy that
  blocks or buffers long-lived connections will break the live updates — see
  [Troubleshooting](#troubleshooting).
- Nothing needs to reach *into* your machine. The app listens on `127.0.0.1`
  only.
- No outbound access at all? Use
  [offline demo mode](#offline-demo-mode-no-launchdarkly-account-needed).

**LaunchDarkly**

- A LaunchDarkly account. A free trial covers everything in this demo.
- Permission to create a flag and read an SDK key in that account.
- You will work in a **non-production environment** — the "Test" environment
  that every new LaunchDarkly project ships with is ideal.

**What is deliberately not production-grade**

This is a demonstration, not a deployment template. It uses Flask's development
server, keeps session state in process memory, and has no authentication. See
[Notes for production use](#notes-for-production-use).

---

## Setup, step by step

### Step 1 — Get the code

```bash
git clone https://github.com/mmccullough24/launchdarkly-landing-page-targeting.git
cd launchdarkly-landing-page-targeting
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

Four packages: the LaunchDarkly server-side Python SDK, Flask, `python-dotenv`,
and `requests`. Nothing else is required.

> Using [uv](https://github.com/astral-sh/uv) instead?
> `uv venv && uv pip install -r requirements.txt`.

**Want to check your Python setup before going further?** Run the offline mode
now — it needs no account and no network:
>
> ```bash
> OFFLINE_DEMO=1 python app.py
> ```
>
> Open <http://127.0.0.1:5000/>, click between the five visitors, and you will
> see the finished demo. Then stop it with `Ctrl-C` and carry on with Step 4 to
> wire up your own account.

### Step 4 — Create the feature flag in LaunchDarkly

The app expects this flag to exist. **You must create it yourself** — SDKs can
read flags but cannot create them.

> **Shortcut:** `python scripts/setup_launchdarkly.py` will create the flag *and*
> configure all the targeting in Steps 4 and 5 for you. It needs an API token —
> see [Automating steps 4 and 5](#automating-steps-4-and-5). The manual steps
> below are worth reading once regardless, because they are what you would
> actually do in the UI.

1. Sign in to [app.launchdarkly.com](https://app.launchdarkly.com).
2. Pick the project and environment you want to demo in, using the project
   selector at the top-left and the environment selector beside it. The default
   project's **Test** environment is a good choice.
3. Go to **Flags** and click **Create flag**.
4. Fill in:
   - **Name:** `Landing page hero`
   - **Key:** `landing-page-hero` — this must match exactly. The app reads it
     from `LD_FLAG_KEY` in your `.env`, which defaults to this value.
   - **Configuration / Flag type:** **Custom**, then choose **String**.
     *Not* boolean — this flag has three variations.
   - **Variations:** add three, with these exact values. The **value** is what
     the code reads; the name is only a label in the UI.

     | # | Value | Name |
     | --- | --- | --- |
     | 1 | `control` | Control |
     | 2 | `spotlight` | Spotlight |
     | 3 | `conversion` | Conversion |

   - **Default variations:** serve **`control`** when targeting is **on**, and
     **`control`** when targeting is **off**. Both default to the control on
     purpose — see the note below.
   - **Client-side SDK availability:** leave every box unchecked. This app
     evaluates the flag server-side; the browser never contacts LaunchDarkly and
     never sees the SDK key.
5. Click **Create flag**.

> **Why both defaults are `control`.** The "off" variation is what every visitor
> gets if someone turns the flag off — your instant, global kill switch. Pointing
> it at the control means the kill switch always returns the page to the
> experience that was already working. The code makes the same choice: if
> LaunchDarkly is unreachable, `config.FLAG_FALLBACK_VARIATION` serves `control`
> too. **The fail-safe direction is always "the thing that already worked."**

### Step 5 — Configure targeting

This is the part the demo is really about. You will add one individual target and
one rule, on the flag's **Targeting** tab.

Make sure the environment selector at the top of the page is set to the same
environment whose SDK key you are about to copy in Step 6. This is the single
most common thing to get wrong.

#### 5a — Individual targeting

Pin one named person to the boldest variation, so the team can see it in
production before any customer does.

1. On the **Targeting** tab, find the **Individual targets** section.
2. Click **Add individual targets** (wording varies slightly by plan) and select
   the **`conversion`** variation.
3. In the target box, type the user key:

   ```
   user-avery-chen
   ```

   Type it exactly and press Enter. LaunchDarkly may not autocomplete it yet —
   that is fine. Autocomplete is populated from contexts the SDK has already
   evaluated, and you have not run the app yet. Typing the key by hand works
   identically.
4. Save.

That is individual targeting: matched **by key**, not by attributes. It is
evaluated before every rule, so a pinned visitor gets the pinned variation no
matter what the rules below say. Part 2 of the walkthrough demonstrates that
precedence directly.

#### 5b — Rule-based targeting

Now describe an *audience* rather than a person: beta testers who are on a paid
plan.

1. Still on the **Targeting** tab, click **Add rule** (or **Add custom rule**).
2. Give it a description: `Beta testers on paid plans`.
3. Build the first clause:
   - **Attribute:** `betaTester`
   - **Operator:** `is one of`
   - **Value:** `true`

   > Type the attribute name by hand if it does not autocomplete. LaunchDarkly
   > learns attribute names once the SDK has evaluated a flag for a context that
   > carries them — so after you have run the app once and clicked through the
   > visitors, these will all be waiting for you in the dropdown.

4. Click **Add condition** to add a second clause to the *same* rule:
   - **Attribute:** `plan`
   - **Operator:** `is one of`
   - **Values:** `enterprise` and `pro` (two separate values)
5. Set the rule to **serve** the **`spotlight`** variation.
6. Save.

Clauses within one rule are joined with **AND**. Both must be true, which is what
makes Sam Okafor — enterprise plan, but not a beta tester — keep the control.

#### 5c — The default rule

Below your rules is the **Default rule**, which applies to everyone who matched
nothing above.

1. Set it to serve **`control`**.
2. Make sure the toggle at the top of the flag page is **on** — otherwise
   targeting is bypassed entirely and everyone gets the off variation.
3. Save.

Your targeting now reads, in evaluation order:

```
1. Individual targets    user-avery-chen                     -> conversion
2. Rule                  betaTester is true
                         AND plan is one of (enterprise, pro) -> spotlight
3. Default rule          everyone else                        -> control
```

#### Automating steps 4 and 5

If you would rather not click through the UI, the repository includes a script
that does all of the above through the LaunchDarkly REST API:

```bash
python scripts/setup_launchdarkly.py          # create the flag + all targeting
python scripts/setup_launchdarkly.py --show   # print the current configuration
python scripts/setup_launchdarkly.py --reset  # remove the targets and rules
```

It needs an API token, which is a **different credential from the SDK key** — the
SDK key reads flags, an API token writes them. Create one under
**Account settings → Authorization → Create token** with the built-in **Writer**
role, then add it to `.env`:

```dotenv
LD_API_TOKEN=api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LD_PROJECT_KEY=default
LD_ENVIRONMENT_KEY=test
```

`LD_PROJECT_KEY` and `LD_ENVIRONMENT_KEY` are the short URL keys, not the display
names — find them under **Project settings → Environments**. The app itself never
uses the API token; only this script does.

### Step 6 — Copy your SDK key

1. In LaunchDarkly, open **Project settings → Environments**.
2. Find the environment you created the flag in.
3. Open its **⋯** (overflow) menu and choose **SDK key → Copy**.

The value starts with `sdk-`. If what you copied starts with `mob-`, or is
labelled "client-side ID", you have the wrong one — this app uses the
**server-side** SDK key.

> **Treat the SDK key as a secret.** It grants read access to every flag in that
> environment. `.env` is git-ignored so it cannot be committed by accident.

### Step 7 — Configure the app

```bash
cp .env.example .env
```

Open `.env` and paste your key:

```dotenv
LAUNCHDARKLY_SDK_KEY=sdk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

That is the only value you must change. Every other setting is optional and
documented inline in that file.

### Step 8 — Run it

```bash
python app.py
```

You should see:

```
==============================================================================
  ABC Company — landing page hero (LaunchDarkly targeting demo)
==============================================================================
  SDK status   : connected to LaunchDarkly
  Feature flag : landing-page-hero
  Variations   : control, spotlight, conversion
  Landing page : http://127.0.0.1:5000/
==============================================================================
```

Open <http://127.0.0.1:5000/>. The inspector's **Live connection** should read
`live (server-sent events)`. If it says `reconnecting…`, see
[Troubleshooting](#troubleshooting).

Leave the app running for the walkthrough.

---

## The demo walkthrough

Put the browser on one side of your screen and LaunchDarkly on the other, so both
are visible. **Do not reload the page at any point** — that is part of the point.

### Part 1 — One flag, three audiences

Click through the five visitors in the top-right switcher and watch the hero and
the inspector change together.

- **Riley Torres** → `control`. The inspector shows `FALLTHROUGH`: no individual
  target, no rule matched. This is what ~40,000 people a day get.
- **Jordan Blake** → `spotlight`, shown as `RULE_MATCH`. Matched by attributes,
  not by name.
- **Priya Raman** → `spotlight`, also `RULE_MATCH`. A different plan, a different
  region, a different device — same rule.
- **Sam Okafor** → `control`. Enterprise, but `betaTester: false`, so the rule's
  second clause fails. Rules are AND.
- **Avery Chen** → `conversion`, shown as `TARGET_MATCH`. Matched by key.

Each visitor's expected outcome is printed under the reason and turns green with
a ✓ when the actual result matches. If any of them stays grey, your targeting
does not yet match what Step 5 described.

Note what did **not** happen: no deploy, no restart, no code change. The audience
for each variation is a product decision, made in the LaunchDarkly UI.

### Part 2 — Individual targeting beats rules

Jordan Blake currently matches the rule and is served `spotlight`. Pin Jordan by
name and watch the individual target win.

1. In LaunchDarkly, add `user-jordan-blake` to the flag's individual targets,
   serving the `conversion` variation. Save.
2. **Watch the browser with Jordan selected.** Without a reload the hero becomes
   `conversion`, and the reason flips from `RULE_MATCH` to `TARGET_MATCH`.
3. Remove that individual target again and Jordan returns to `spotlight`.

Nothing about the rule changed — it still matches Jordan perfectly. The
individual target is simply evaluated first.

> **Why not try this with Avery Chen?** Because Avery's `plan` is `internal`,
> which fails the rule's `plan is one of (enterprise, pro)` clause. Remove
> Avery's individual target and the result is `control` via `FALLTHROUGH`, not
> `spotlight` — there is no rule for Avery to fall back to. That is worth seeing
> once too: individual targeting is often used for exactly this, reaching someone
> no rule covers.

That precedence — individual targets, then rules in order, then the default rule
— is what lets you make an exception for one person without touching the rule
that serves everyone else.

### Part 3 — Widen the audience with one edit

Right now `spotlight` reaches beta testers on paid plans. Suppose it is going
well and you want every enterprise customer, beta tester or not.

In the rule, delete the `betaTester` clause and save. **Sam Okafor** — who was
seeing the control a moment ago — switches to `spotlight` live, while Riley
Torres, on the free plan, does not move.

That is the whole risk-management story of the revamp: the blast radius is a
value you choose, and you can change it in seconds without shipping code.

### Part 4 — A percentage rollout

Rules and individual targets are exact. For a gradual rollout, change the
**Default rule** from "serve `control`" to a **percentage rollout** — say 90%
`control`, 10% `spotlight`. Save.

Each visitor is bucketed consistently by their context key, so a given person
always lands in the same bucket. Click between Riley and Sam and note the
reason line: it still reads `FALLTHROUGH`, because the default rule is what
served them, but they may now get different heroes.

### Part 5 — Measure it, then kill it

1. Click the hero's primary button as different visitors. Each click sends a
   `landing-page-cta-click` custom metric event tagged with the variation that
   was served. Attach that metric to the flag in LaunchDarkly and you can compare
   conversion per variation while the revamp is live — the difference between
   "I prefer the new one" and "the new one converts better".
2. Now turn the flag's top toggle **off** and save. Every open tab drops to the
   control at once, and the reason changes to `OFF`. That is the global kill
   switch: one click, no deploy, everyone safe.

---

## How it works

### The flow, end to end

```
   You change targeting
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
                                        │    ├─ variation_detail(ctx)    │
                                        │    │    value + WHY            │
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
                                        │  swaps #hero-mount in place    │
                                        └────────────────────────────────┘
```

Two push hops, and neither is a poll:

1. **LaunchDarkly → server.** The SDK's default streaming data source keeps a
   connection open, so targeting changes arrive in milliseconds. That is what
   `ld_client.add_flag_value_change_listener()` hooks into. It is *value*-based
   and *context*-aware: a session is notified only when the value **for that
   person** changes. Add one name to the individual targets and only that
   person's tab is told.
2. **Server → browser.** Each open tab holds a Server-Sent Events connection.
   When a listener fires, the server re-renders the hero and pushes the HTML down
   that tab's stream.

The browser never talks to LaunchDarkly and never sees the SDK key.

### Where targeting actually happens

Nowhere in this codebase. That is the point worth making to a prospect.

There is no `if plan == "enterprise"` anywhere in the app. The code sends a
context describing *who this is*, and LaunchDarkly decides *what they get*:

```python
context   = contexts.build_context(visitor_id)   # who they are
evaluation = ld_client.evaluate(context)          # what LaunchDarkly decided
view       = hero.build_hero(evaluation["variation"])
```

Adding a rule for `region is EMEA`, or pinning three more people by name, or
switching to a percentage rollout, changes nothing in this repository.

### Seeing *why*, not just *what*

`ld_client.evaluate()` uses `variation_detail()` rather than plain `variation()`.
Both return the value; `variation_detail()` also returns the evaluation **reason**,
which is what the inspector renders:

| Reason kind | Means | Shown as |
| --- | --- | --- |
| `TARGET_MATCH` | Matched an individual target, by key | individual (purple) |
| `RULE_MATCH` | Matched a targeting rule, by attributes | rule (blue) |
| `FALLTHROUGH` | Matched nothing; the default rule applied | default (grey) |
| `OFF` | Targeting is off; the off variation was served | off (amber) |
| `ERROR` | Flag missing, SDK not ready — fallback served | error (red) |

In production you would normally call `variation()` and skip the reason;
requesting detail on every evaluation has a small cost. It is used here because
the reason *is* the demo.

### File map

| File | What it does |
| --- | --- |
| `app.py` | Flask routes, the SSE endpoint, startup/shutdown. Start here. |
| `ld_client.py` | Every LaunchDarkly SDK call: init, evaluate, listener, custom events, and the offline data source. |
| `contexts.py` | The five visitors and the LaunchDarkly `Context` built for each. **The targetable attributes are defined here.** |
| `components/hero.py` | The flagged component — all three heroes, side by side. Knows nothing about LaunchDarkly. |
| `session_hub.py` | Tracks open browser tabs; registers and tears down one flag listener per tab. |
| `templates/hero.html` | Renders one hero from its view model. |
| `templates/index.html` | Page shell, visitor switcher, and the targeting inspector. |
| `scripts/setup_launchdarkly.py` | Optional: creates the flag and all targeting through the REST API. |
| `config.py` | Reads `.env`. Every setting is documented in place. |

### The pattern worth copying

The flag is evaluated at **one place, at the edge** (`app.py`), and the result is
handed to the component as a plain string:

```python
variation = ld_client.evaluate(context)["variation"]
view      = hero.build_hero(variation)
```

`components/hero.py` never imports the SDK. That keeps the component testable
with no account and no network, lets a designer iterate on a variation without
touching flag code, and means that when the revamp is finished you delete two
functions and archive the flag rather than unpicking SDK calls scattered through
the view layer.

`build_hero()` also falls back to the control for an unrecognised variation. If
someone adds a fourth variation in the LaunchDarkly UI before this code knows
about it, visitors get the known-good hero instead of a 500.

---

## Offline demo mode (no LaunchDarkly account needed)

To see the whole demo with no account, no key, and no network:

```bash
OFFLINE_DEMO=1 python app.py
```

The flag — including its individual target and its targeting rule — is served
from an in-process data source, and the page grows two buttons that turn
targeting on and off.

**This is a faithful demo, not a mock.** The in-process source publishes the real
LaunchDarkly flag payload (targets, rule clauses, fallthrough) through the same
change-broadcasting layer the streaming connection uses. The SDK's own targeting
engine evaluates it, and the same `flag_tracker` listener fires. Every
`TARGET_MATCH` and `RULE_MATCH` you see offline is a genuine verdict from the SDK
— only the transport differs.

It is deliberately *not* built on the SDK's `TestData` source, which writes
straight to the feature store and bypasses change broadcasting, so flag listeners
would never fire.

---

## Troubleshooting

**`*** LaunchDarkly did not initialize.`**
The SDK could not fetch flags within its startup window. In order of likelihood:
the key in `.env` is a client-side ID or mobile key rather than an `sdk-` key;
the key was copied with a trailing space; or outbound HTTPS to
`stream.launchdarkly.com` is blocked. Test the last one with
`curl -sSf -o /dev/null https://app.launchdarkly.com`.

**Everyone gets `control`, and the reason says the flag "was not found".**
The flag key does not match. It must be exactly `landing-page-hero` (or whatever
you set `LD_FLAG_KEY` to), in the **same environment** as the SDK key you copied.

**Everyone gets `control` and the reason says `FALLTHROUGH`.**
The flag exists and is being evaluated, but no targeting matched. Either the
individual target and rule were not saved, or they were saved in a different
environment from the SDK key you are using. The environment selector in the
LaunchDarkly UI is independent of which key you copied — this is the single most
common cause.

**Everyone gets `control` and the reason says `OFF`.**
The flag's top toggle is off, so targeting is bypassed. Turn it on.

**Avery Chen gets `spotlight` instead of `conversion`.**
The individual target did not save, so the rule is matching instead. Re-check
Step 5a: the key must be exactly `user-avery-chen`, targeted to the `conversion`
variation.

**Sam Okafor gets `spotlight` instead of `control`.**
Your two clauses are probably in two separate rules rather than as two conditions
in one rule. Separate rules are OR; conditions within a rule are AND. Delete one
and use **Add condition** instead of **Add rule**.

**The attribute names do not autocomplete in the rule builder.**
LaunchDarkly populates that list from contexts it has already seen. Run the app
and click through all five visitors once, then reload the LaunchDarkly page. You
can always type the names by hand — the rules work identically.

**The page loads but "Live connection" says `reconnecting…`.**
Something between the browser and the app is buffering. Behind nginx, set
`proxy_buffering off` for `/api/stream`. Otherwise check for a corporate proxy or
a browser extension that terminates long-lived requests.

**Changing targeting in LaunchDarkly changes nothing in the browser.**
Work down this list:
1. Is the currently selected visitor actually affected by the change? A rule that
   only serves beta testers will not notify Riley Torres — that is correct
   behaviour, and the point of Part 1.
2. Are you editing the same environment your SDK key came from?
3. Check the terminal running `app.py`. Every listener firing logs a line like
   `Flag 'landing-page-hero' changed to 'spotlight' for jordan`.

**`Address already in use` on startup.**
Something else owns port 5000 — on macOS, usually AirPlay Receiver. Turn it off
in **System Settings → General → AirDrop & Handoff**, or use another port:
`PORT=5050 python app.py`.

**`ModuleNotFoundError: No module named 'ldclient'`.**
The virtual environment is not active. Re-run the activate command from Step 2 —
your prompt should show `(.venv)`.

**`scripts/setup_launchdarkly.py` returns HTTP 401 or 403.**
The API token is missing, mistyped, or lacks write access. It must be an API
token (`api-…`), not the SDK key. HTTP 404 usually means `LD_PROJECT_KEY` or
`LD_ENVIRONMENT_KEY` is a display name rather than the short key.

---

## Notes for production use

What this demo does that a real deployment should do differently:

- **Web server.** Flask's development server is single-process and not hardened.
  Use gunicorn or uvicorn behind a real proxy. Each worker process gets its own
  SDK client, which is fine and expected.
- **Session state.** `SessionHub` is in-process memory: it does not survive a
  restart and does not span workers. With multiple workers each holds its own
  listeners and pushes to its own connected tabs, which still works. A shared bus
  (Redis pub/sub) is only needed for cross-process fan-out.
- **One client, forever.** The SDK client is created once at startup and reused.
  Creating one per request would open a streaming connection per request.
- **Context keys.** Use a stable identifier. Percentage rollouts and individual
  targeting both depend on the key being the same for the same person on every
  visit. For genuinely anonymous landing page traffic, generate a key once and
  persist it in a cookie, and set `anonymous: true` on the context so those users
  do not count towards your MAU.
- **Don't request detail you do not use.** `variation_detail()` is used here so
  the inspector can explain itself. Production code should call `variation()`.
- **Secrets.** The SDK key belongs in your secret manager, not a `.env` file on
  disk. The API token used by the setup script is more powerful still — it can
  write flags — and should never be deployed with the app.
- **Flag lifecycle.** A release flag is temporary. Once a hero wins, delete the
  other two branches and archive the flag. LaunchDarkly's code references and
  flag status views exist to stop temporary flags becoming permanent debt.
- **Experimentation.** The `landing-page-cta-click` event is illustrative. For a
  real landing page test you would define a conversion metric in LaunchDarkly and
  run an experiment, so the winner is decided by statistics rather than by
  whoever is most senior in the room.

---

## Related

This repository is Part 2 of a pair. Part 1 —
[launchdarkly-part-1-release-and-remediate](https://github.com/mmccullough24/launchdarkly-part-1-release-and-remediate)
— covers releasing a feature behind a flag and remediating it instantly with a
kill switch and flag triggers. This part focuses on **who** gets the feature.

## License

MIT — see [LICENSE](LICENSE).
