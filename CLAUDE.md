# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-process Flask demo of LaunchDarkly **targeting**. The ABC Company landing page hero is
wrapped in a string flag, `landing-page-hero`, with three variations (`control` / `spotlight` /
`conversion`). Five demo visitors exercise every targeting path: one matched by an individual
target, two by a rule, two by the default rule. A "targeting inspector" rail renders the
LaunchDarkly evaluation reason so the mechanism behind each decision is visible.

`README.md` carries the LaunchDarkly-side setup (creating the flag, building the individual target
and the rule) and the demo walkthrough.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set LAUNCHDARKLY_SDK_KEY (must start with `sdk-`)
python app.py                 # http://127.0.0.1:5000/

OFFLINE_DEMO=1 python app.py  # no account, no network, targeting fully configured
PORT=5050 python app.py       # any config.py setting can be overridden inline

python scripts/setup_launchdarkly.py          # create flag + targeting via REST API
python scripts/setup_launchdarkly.py --show   # print current targeting config
python scripts/setup_launchdarkly.py --reset  # remove targets and rules

curl localhost:5000/healthz   # {ok, sessions, flagKey}
```

**There is no test suite, linter, or CI.** `OFFLINE_DEMO=1` is the verification path, and it is a
real end-to-end exercise of the SDK's targeting engine rather than a mock — use it to check any
change to the flag, context, or SSE plumbing. This one-liner asserts all five targeting paths:

```bash
OFFLINE_DEMO=1 python -c "
import ld_client, contexts
ld_client.initialize()
for vid, v in contexts.VISITORS.items():
    ev = ld_client.evaluate(contexts.build_context(vid))
    ok = ev['variation'] == v['expected_variation'] and ev['reasonKind'] == v['expected_via']
    print(vid, ev['variation'], ev['reasonKind'], 'OK' if ok else 'MISMATCH')
"
```

Running against a real account requires a flag matching `LD_FLAG_KEY` to already exist in the same
environment as the SDK key; SDKs cannot create flags. A key mismatch surfaces in the inspector's
reason line as *"was not found in this environment"* rather than as an error.

## Architecture

Two push hops, neither of them a poll:

```
LaunchDarkly --(SDK streaming connection)--> flag_tracker listener  [SDK bg thread]
             --> SessionHub → per-tab queue --> /api/stream (SSE)   [request thread]
             --> static/js/app.js swaps #hero-mount in place
```

- **`app.py`** — routes, SSE endpoint, startup/shutdown. `build_state()` is the single place that
  assembles what the browser needs; it always re-evaluates the flag so the inspector can explain
  *why*, but an authoritative variation from the listener wins over that re-read.
- **`ld_client.py`** — the only module that imports `ldclient`. Init, `variation_detail` evaluation,
  reason→mechanism mapping, the flag value change listener, custom events, and `_OfflineDataSource`.
- **`contexts.py`** — the five visitors. The attributes set here (`role`, `plan`, `betaTester`,
  `region`, `accountAgeDays`, `deviceType`) are exactly what targeting rules can be built on.
  `expected_variation` / `expected_via` drive the inspector's ✓ and are demo metadata only.
- **`components/hero.py`** — all three heroes, selected by `build_hero(variation)`.
- **`session_hub.py`** — one `Session` per browser tab, each owning a context, one flag listener,
  and a bounded queue. Registry mutations are lock-guarded because the SDK fires listeners on its
  own thread.
- **`scripts/setup_launchdarkly.py`** — REST API automation. Semantic patch instructions reference
  variations by UUID, so it always GETs the flag before writing targeting.

### Invariants worth preserving

Load-bearing for the demo; changing them breaks it subtly rather than loudly.

- **No targeting logic in this codebase.** There is no `if plan == "enterprise"` anywhere, and there
  must not be — the demo's whole argument is that LaunchDarkly owns that decision. The code sends a
  context and renders whatever variation comes back.
- **The flag is evaluated at the edge, once.** `app.py` evaluates and passes a plain string down.
  `components/hero.py` must never import the SDK.
- **Fail safe toward the control.** `FLAG_FALLBACK_VARIATION = "control"`, and `build_hero()` falls
  back to the control for any unrecognised variation rather than raising.
- **One SDK client per process**, created at startup — hence `use_reloader=False`.
- **`threaded=True` is required** — every open tab holds an SSE connection, and a worker thread.
- **Listener callbacks run on an SDK background thread.** `SessionHub._handle_change` catches
  everything on purpose: an escaping exception kills that thread and silently stops all future
  notifications. `render_hero()` pushes a Flask app context for the same reason — it is called from
  both request and SDK threads.
- **The CTA is bound by delegation** in `static/js/app.js`, because the hero it lives in is replaced
  wholesale on every variation change.
- **Three places define the targeting** and must stay in sync when customising: `contexts.py`
  (attributes + expectations), `ld_client.py` `_OfflineDataSource._flag_data()` (the offline
  payload), and `scripts/setup_launchdarkly.py` (the REST instructions). The README describes the
  same configuration a fourth time, in UI terms.

### The offline mode is not `TestData`

`_OfflineDataSource` in `ld_client.py` deliberately avoids the SDK's built-in `TestData` source,
which writes straight to the feature store and bypasses the change-broadcasting layer — flag
listeners never fire. The custom source writes through `config.data_source_update_sink` exactly as
the real streaming processor does, publishing a genuine LaunchDarkly flag payload (individual
targets, rule clauses, fallthrough). The SDK's own evaluator applies it, so offline
`TARGET_MATCH` / `RULE_MATCH` reasons are real verdicts, not simulated ones.

## Conventions

Module docstrings carry the teaching load — they explain *why* a LaunchDarkly choice was made, not
just what the code does, and inline comments flag the places a user has to substitute their own
values. This repo is a sales artifact read by prospective customers as much as it is run; match
that density when editing, and keep the LaunchDarkly vocabulary in the UI copy identical to the
vocabulary in the LaunchDarkly console ("individual target", "targeting rule", "default rule").
