#!/usr/bin/env python3
"""Create the demo flag and its targeting in LaunchDarkly, via the REST API.

This is an OPTIONAL convenience. Everything it does can be done by clicking
through the LaunchDarkly UI, and README.md -> Step 4 and Step 5 describe exactly
how. Use this script if you would rather not click, or if you re-run the demo
often and want a repeatable starting point.

What it creates:

  * a string flag `landing-page-hero` with three variations:
        control / spotlight / conversion
  * an INDIVIDUAL TARGET   — user-avery-chen -> conversion
  * a TARGETING RULE       — betaTester is true AND plan in (enterprise, pro)
                             -> spotlight
  * a DEFAULT RULE         — everyone else -> control
  * targeting turned on

Usage:

    python scripts/setup_launchdarkly.py            # create + configure
    python scripts/setup_launchdarkly.py --show     # print current config only
    python scripts/setup_launchdarkly.py --reset    # remove targets and rules

Requires `LD_API_TOKEN` in your `.env` (Account settings -> Authorization ->
Create token, "Writer" role). This is a *different* credential from the SDK key:
the SDK key reads flags, the API token writes them. The app itself never uses
the API token.
"""

import sys
from pathlib import Path

import requests

# Make the project root importable so this script shares the app's config.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

TIMEOUT = 15

# LaunchDarkly's "semantic patch" content type. It lets you describe the change
# you want ("add this rule") rather than a JSON Patch document, so the request
# cannot clobber a concurrent edit by someone else on your team.
SEMANTIC_PATCH = "application/json; domain-model=launchdarkly.semanticpatch"

# The individual to pin, and the rule to build. These mirror contexts.py and the
# README exactly — change them in all three places if you customise the demo.
INDIVIDUAL_TARGET_KEY = "user-avery-chen"
INDIVIDUAL_TARGET_VARIATION = "conversion"

RULE_DESCRIPTION = "Beta testers on paid plans"
RULE_VARIATION = "spotlight"
RULE_CLAUSES = [
    {"contextKind": "user", "attribute": "betaTester", "op": "in", "values": [True], "negate": False},
    {"contextKind": "user", "attribute": "plan", "op": "in", "values": ["enterprise", "pro"], "negate": False},
]

FALLTHROUGH_VARIATION = "control"

VARIATIONS = [
    {
        "value": "control",
        "name": "Control",
        "description": "The hero currently in production. The safe default.",
    },
    {
        "value": "spotlight",
        "name": "Spotlight",
        "description": "The redesign: social proof and product metrics above the fold.",
    },
    {
        "value": "conversion",
        "name": "Conversion",
        "description": "Aggressive offer with urgency and a testimonial. Individually targeted only.",
    },
]


class SetupError(RuntimeError):
    """Anything that should stop the script with a readable message."""


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------


def _headers(semantic: bool = False) -> dict:
    return {
        "Authorization": config.LD_API_TOKEN,
        "Content-Type": SEMANTIC_PATCH if semantic else "application/json",
    }


def _url(path: str) -> str:
    return f"{config.LD_API_BASE_URL}/api/v2{path}"


def _check(response: requests.Response, what: str) -> dict:
    if response.ok:
        return response.json() if response.content else {}
    # The API's error bodies explain the problem (bad token, wrong project key,
    # flag already exists) and never echo the token back.
    raise SetupError(f"{what} failed — HTTP {response.status_code}: {response.text[:400]}")


def get_flag() -> dict | None:
    """Fetch the flag, or None if it does not exist yet."""
    response = requests.get(
        _url(f"/flags/{config.LD_PROJECT_KEY}/{config.FLAG_KEY}"),
        params={"env": config.LD_ENVIRONMENT_KEY},
        headers=_headers(),
        timeout=TIMEOUT,
    )
    if response.status_code == 404:
        return None
    return _check(response, "Reading the flag")


def create_flag() -> dict:
    """Create the multivariate string flag."""
    body = {
        "key": config.FLAG_KEY,
        "name": "Landing page hero",
        "description": (
            "Controls which hero the ABC Company landing page serves. "
            "Created by scripts/setup_launchdarkly.py."
        ),
        "kind": "multivariate",
        "variations": VARIATIONS,
        # Serve the control by default in every environment, both when targeting
        # is on and when it is off — the fail-safe direction.
        "defaults": {"onVariation": 0, "offVariation": 0},
        # Mark it temporary: a release flag is meant to be removed once the
        # revamp is fully rolled out.
        "temporary": True,
        "tags": ["demo", "landing-page"],
        # This demo evaluates server-side, so the browser never needs the flag.
        "clientSideAvailability": {"usingEnvironmentId": False, "usingMobileKey": False},
    }
    return _check(
        requests.post(_url(f"/flags/{config.LD_PROJECT_KEY}"), json=body, headers=_headers(), timeout=TIMEOUT),
        "Creating the flag",
    )


def patch(instructions: list[dict], comment: str) -> dict:
    """Apply a list of semantic-patch instructions to the flag."""
    body = {
        "environmentKey": config.LD_ENVIRONMENT_KEY,
        "instructions": instructions,
        "comment": comment,
    }
    return _check(
        requests.patch(
            _url(f"/flags/{config.LD_PROJECT_KEY}/{config.FLAG_KEY}"),
            json=body,
            headers=_headers(semantic=True),
            timeout=TIMEOUT,
        ),
        "Updating targeting",
    )


# ---------------------------------------------------------------------------
# Reading the flag's current shape
# ---------------------------------------------------------------------------


def variation_ids(flag: dict) -> dict[str, str]:
    """Map each variation's value to the UUID LaunchDarkly assigned it.

    Semantic patch instructions reference variations by id, not by index, so we
    always have to read the flag before we can write targeting for it.
    """
    return {str(v["value"]): v["_id"] for v in flag["variations"]}


def environment(flag: dict) -> dict:
    env = flag.get("environments", {}).get(config.LD_ENVIRONMENT_KEY)
    if env is None:
        raise SetupError(
            f"Environment '{config.LD_ENVIRONMENT_KEY}' not found on this flag. "
            f"Set LD_ENVIRONMENT_KEY in .env to the environment's short key "
            f"(e.g. 'test' or 'production')."
        )
    return env


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def show() -> None:
    """Print the flag's current targeting configuration."""
    flag = get_flag()
    if flag is None:
        print(f"Flag '{config.FLAG_KEY}' does not exist in project '{config.LD_PROJECT_KEY}'.")
        return

    env = environment(flag)
    by_id = {v["_id"]: str(v["value"]) for v in flag["variations"]}

    print(f"Flag        : {flag['key']} ({flag['kind']})")
    print(f"Environment : {config.LD_ENVIRONMENT_KEY}")
    print(f"Targeting   : {'ON' if env.get('on') else 'OFF'}")
    print(f"Variations  : {', '.join(str(v['value']) for v in flag['variations'])}")

    targets = env.get("targets", []) + env.get("contextTargets", [])
    print("\nIndividual targets:")
    if not targets:
        print("  (none)")
    for target in targets:
        variation = flag["variations"][target["variation"]]["value"]
        for value in target.get("values", []):
            print(f"  {value}  ->  {variation}")

    print("\nTargeting rules:")
    rules = env.get("rules", [])
    if not rules:
        print("  (none)")
    for index, rule in enumerate(rules):
        served = by_id.get(rule.get("variation")) if isinstance(rule.get("variation"), str) else None
        if served is None and isinstance(rule.get("variation"), int):
            served = str(flag["variations"][rule["variation"]]["value"])
        print(f"  #{index + 1} {rule.get('description') or '(no description)'}  ->  {served}")
        for clause in rule.get("clauses", []):
            negate = "NOT " if clause.get("negate") else ""
            print(f"       {negate}{clause['attribute']} {clause['op']} {clause['values']}")

    fallthrough = env.get("fallthrough", {})
    if "variation" in fallthrough:
        index = fallthrough["variation"]
        served = flag["variations"][index]["value"] if isinstance(index, int) else by_id.get(index)
        print(f"\nDefault rule: everyone else -> {served}")
    elif "rollout" in fallthrough:
        print("\nDefault rule: percentage rollout")


def reset() -> None:
    """Remove the individual target and the rules, leaving the flag in place."""
    flag = get_flag()
    if flag is None:
        raise SetupError(f"Flag '{config.FLAG_KEY}' does not exist — nothing to reset.")

    env = environment(flag)
    ids = variation_ids(flag)
    instructions: list[dict] = []

    for target in env.get("targets", []):
        value = str(flag["variations"][target["variation"]]["value"])
        instructions.append({
            "kind": "removeTargets",
            "variationId": ids[value],
            "values": target.get("values", []),
        })
    for rule in env.get("rules", []):
        instructions.append({"kind": "removeRule", "ruleId": rule["_id"]})

    if not instructions:
        print("No individual targets or rules to remove.")
        return

    patch(instructions, "Reset by scripts/setup_launchdarkly.py")
    print(f"Removed {len(instructions)} targeting item(s). The flag itself was left in place.")


def setup() -> None:
    """Create the flag if needed, then apply the demo's targeting."""
    flag = get_flag()

    if flag is None:
        print(f"Creating flag '{config.FLAG_KEY}' in project '{config.LD_PROJECT_KEY}'…")
        create_flag()
        flag = get_flag()
        if flag is None:
            raise SetupError("Flag was created but could not be read back.")
        print("  created.")
    else:
        print(f"Flag '{config.FLAG_KEY}' already exists — leaving it as it is.")
        values = {str(v["value"]) for v in flag["variations"]}
        expected = {v["value"] for v in VARIATIONS}
        if values != expected:
            raise SetupError(
                f"The existing flag's variations are {sorted(values)}, but this demo "
                f"expects {sorted(expected)}. Either delete the flag and re-run this "
                f"script, or set LD_FLAG_KEY in .env to a new key."
            )

    env = environment(flag)
    ids = variation_ids(flag)
    instructions: list[dict] = []

    # --- targeting on -----------------------------------------------------
    if not env.get("on"):
        instructions.append({"kind": "turnFlagOn"})

    # --- individual targeting ---------------------------------------------
    # Evaluated before every rule, so a pinned visitor gets the pinned variation
    # whatever the rules below say. Note that Avery's plan is `internal`, which
    # does not satisfy the beta-tester rule — so this target is also the only
    # thing giving Avery anything other than the control.
    already_targeted = any(
        INDIVIDUAL_TARGET_KEY in target.get("values", [])
        for target in env.get("targets", [])
    )
    if already_targeted:
        print(f"Individual target for '{INDIVIDUAL_TARGET_KEY}' already present — skipping.")
    else:
        instructions.append({
            "kind": "addTargets",
            "variationId": ids[INDIVIDUAL_TARGET_VARIATION],
            "values": [INDIVIDUAL_TARGET_KEY],
        })

    # --- rule-based targeting ---------------------------------------------
    rule_exists = any(
        rule.get("description") == RULE_DESCRIPTION for rule in env.get("rules", [])
    )
    if rule_exists:
        print(f"Rule '{RULE_DESCRIPTION}' already present — skipping.")
    else:
        instructions.append({
            "kind": "addRule",
            "description": RULE_DESCRIPTION,
            "variationId": ids[RULE_VARIATION],
            "clauses": RULE_CLAUSES,
        })

    # --- default rule ------------------------------------------------------
    instructions.append({
        "kind": "updateFallthroughVariationOrRollout",
        "variationId": ids[FALLTHROUGH_VARIATION],
    })

    patch(instructions, "Configured by scripts/setup_launchdarkly.py")
    print(f"Applied {len(instructions)} change(s).\n")
    show()
    print(
        "\nDone. Start the app with `python app.py` and switch between visitors:\n"
        "  Avery Chen   -> conversion, via an individual target\n"
        "  Jordan Blake -> spotlight,  via the targeting rule\n"
        "  Riley Torres -> control,    via the default rule"
    )


def main() -> int:
    command = (sys.argv[1] if len(sys.argv) > 1 else "").lower()

    # Help works without credentials, so someone can discover what this does
    # before deciding whether to create a token for it.
    if command in ("-h", "--help"):
        print(__doc__)
        return 0

    if not config.LD_API_TOKEN:
        print(
            "error: LD_API_TOKEN is not set.\n\n"
            "  This script uses the LaunchDarkly REST API, which needs an access\n"
            "  token — a different credential from the SDK key.\n\n"
            "  LaunchDarkly UI: Account settings -> Authorization -> Create token,\n"
            "  with the built-in 'Writer' role. Then add it to your .env:\n\n"
            "      LD_API_TOKEN=api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n\n"
            "  You can skip this script entirely and configure the flag by hand —\n"
            "  see README.md, Step 4 and Step 5.",
            file=sys.stderr,
        )
        return 1

    try:
        if command in ("", "--setup"):
            setup()
        elif command == "--show":
            show()
        elif command == "--reset":
            reset()
        else:
            print(f"unknown argument: {command} (try --help)", file=sys.stderr)
            return 2
    except SetupError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"\nerror: could not reach the LaunchDarkly API: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
