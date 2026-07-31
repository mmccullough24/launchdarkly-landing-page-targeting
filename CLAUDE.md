# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-process Flask demo ("ABC Company Operations Cloud") that shows LaunchDarkly decoupling
deploy from release: both versions of an Order Insights panel ship in the binary, and the boolean
flag `release-order-insights-v2` decides which one each persona sees — switching live, with no page
reload. See `README.md` for the full narrative and the LaunchDarkly-side setup (creating the flag,
targeting rules, triggers).

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set LAUNCHDARKLY_SDK_KEY (must start with `sdk-`)
python app.py                 # http://127.0.0.1:5000/

OFFLINE_SELF_TEST=1 python app.py   # no account, no network; page grows flag-toggle buttons
PORT=5050 python app.py             # any config.py setting can be overridden inline

./scripts/remediate.sh            # kill switch: flag OFF (trigger URL, else REST API)
./scripts/remediate.sh --on       # re-enable; REST API only, needs LD_API_TOKEN
./scripts/remediate.sh --status   # needs LD_API_TOKEN

curl localhost:5000/healthz       # {ok, sessions, flagKey}
```

**There is no test suite, linter, or CI in this repo.** `OFFLINE_SELF_TEST=1` is the only automated
verification path — and it is a real end-to-end exercise of the listener chain, not a mock, so use it
to validate changes to the flag/SSE plumbing.

Running against a real account requires a flag whose key matches `LD_FLAG_KEY` to already exist in
the same LaunchDarkly environment as the SDK key; SDKs cannot create flags. A key mismatch surfaces
in the UI's reason line as *"was not found in this environment"* rather than as an error.

## Architecture

Two push hops, neither of them a poll:

```
LaunchDarkly --(SDK streaming connection)--> flag_tracker listener  [SDK bg thread]
             --> SessionHub → per-tab queue --> /api/stream (SSE)   [request thread]
             --> static/js/app.js swaps #feature-panel in place
```

- **`app.py`** — routes, SSE endpoint, startup/shutdown. `build_state()` is the single place that
  assembles what the browser needs; it always re-evaluates the flag so the UI can explain *why* a
  value was served, but an authoritative `flag_on` from the listener wins over that re-read.
- **`ld_integration.py`** — the only module that imports `ldclient`. Init, `variation_detail`
  evaluation, the flag value change listener, custom events, and the offline data source.
- **`session_hub.py`** — one `Session` per open browser tab, each owning a LaunchDarkly context, one
  flag listener, and a bounded queue. Registry mutations are lock-guarded because the SDK fires
  listeners on its own thread.
- **`personas.py`** — three fixed users. The attributes set here (`role`, `betaTester`, `plan`) are
  exactly what targeting rules can be built on in the LaunchDarkly UI.
- **`features/order_insights.py`** — both code paths (`legacy_view()` / `v2_view()`), selected by
  `build_view(flag_on)`.
- **`remediation.py`** / **`scripts/remediate.sh`** — the kill switch, two implementations of the
  same two mechanisms (trigger URL preferred, REST semantic patch as fallback).

### Invariants worth preserving

These are load-bearing for the demo; changing them tends to break it subtly rather than loudly.

- **The flag check lives at the edge, once.** `app.py` evaluates and passes a plain bool down.
  `features/order_insights.py` must never import the SDK — that is the pattern the demo is teaching,
  and it keeps the feature testable without a LaunchDarkly connection.
- **Fail safe toward the already-shipped path.** `FLAG_FALLBACK_VALUE = False`, so an unreachable
  LaunchDarkly, a bad key, or a missing flag all serve v1.
- **One SDK client per process, created at startup.** Hence `use_reloader=False`; a client per
  request would open a streaming connection per request.
- **`threaded=True` is required** — every open tab holds an SSE connection, and therefore a worker
  thread, for as long as it is open.
- **Listener callbacks run on an SDK background thread.** `SessionHub._handle_change` catches
  everything on purpose: an escaping exception kills that thread and silently stops all future
  notifications. `render_panel()` pushes a Flask app context for the same reason — it is called from
  both request and SDK threads.
- **Listeners are value-based and context-aware**, so a rule change that only affects beta testers
  notifies only those sessions. A persona switch closes and re-opens the stream to register a
  listener for the new context.
- **Trigger URLs and API tokens are credentials and are never logged** — `remediation.py` logs the
  exception type only. Keep it that way when adding error handling.

### The offline self-test is not `TestData`

`_SelfTestDataSource` in `ld_integration.py` deliberately avoids the SDK's built-in `TestData`
source, which writes straight to the feature store and bypasses the change-broadcasting layer — flag
listeners never fire. The custom source writes through `config.data_source_update_sink` exactly as
the real streaming processor does, so the same listener path runs offline. Note that the comment on
`OFFLINE_SELF_TEST` in `config.py` still says "TestData source" and is stale.

## Conventions

Module docstrings here carry the teaching load — they explain *why* a choice was made, not just
what the code does, and inline comments flag LaunchDarkly-specific reasoning. Match that density
when editing; this repo is read as much as it is run.
