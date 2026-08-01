"""The visitors ABC Company's landing page is evaluated for.

A LaunchDarkly **context** describes who a flag is being evaluated for. Every
attribute set here becomes something you can target on in the LaunchDarkly UI
*without changing or redeploying this code* — which is the whole point: the
targeting decisions for the landing page revamp move from an engineering
release cycle to a product decision that takes seconds.

The demo ships five fixed visitors so you can switch between them in the browser
and watch one flag serve three different heroes. Between them they exercise
every targeting path:

    Avery Chen   -> matched by an INDIVIDUAL TARGET  (takes precedence over any
                                                      rule; note that Avery's
                                                      plan is `internal`, so no
                                                      rule matches Avery anyway
                                                      — remove the target and
                                                      Avery falls through to
                                                      the control)
    Jordan Blake -> matched by a  TARGETING RULE     (enterprise + beta tester)
    Priya Raman  -> matched by the same RULE         (pro + beta tester)
    Sam Okafor   -> falls through to the DEFAULT     (enterprise, but not a
                                                      beta tester — proves the
                                                      rule's AND semantics)
    Riley Torres -> falls through to the DEFAULT     (a typical visitor: this
                                                      is ~all of the 40,000/day)

`expected_variation` and `expected_via` are not used for evaluation — the SDK
decides that. They are displayed in the UI so you can confirm your targeting is
configured the way the README describes.
"""

from ldclient import Context

# The context kind. "user" is LaunchDarkly's default kind; a real landing page
# might also send a "device" or "organization" context and target on those.
CONTEXT_KIND = "user"

VISITORS = {
    "avery": {
        "key": "user-avery-chen",
        "name": "Avery Chen",
        "email": "avery.chen@abccompany.example",
        "title": "QA Engineer, ABC Company",
        # --- targetable attributes -----------------------------------------
        "role": "internal-qa",
        "plan": "internal",
        "betaTester": True,
        "region": "AMER",
        "accountAgeDays": 980,
        "deviceType": "desktop",
        # --- demo metadata (not sent to LaunchDarkly) ----------------------
        "blurb": "Internal QA. Pinned to the boldest variation by name so the "
                 "team can test it in production before anyone else sees it.",
        "expected_variation": "conversion",
        "expected_via": "TARGET_MATCH",
    },
    "jordan": {
        "key": "user-jordan-blake",
        "name": "Jordan Blake",
        "email": "jordan.blake@northwind.example",
        "title": "Operations Lead, Northwind Trading",
        "role": "customer",
        "plan": "enterprise",
        "betaTester": True,
        "region": "EMEA",
        "accountAgeDays": 612,
        "deviceType": "desktop",
        "blurb": "Enterprise customer who opted in to early access. Matched by "
                 "the targeting rule, not by name.",
        "expected_variation": "spotlight",
        "expected_via": "RULE_MATCH",
    },
    "priya": {
        "key": "user-priya-raman",
        "name": "Priya Raman",
        "email": "priya.raman@lumen.example",
        "title": "Founder, Lumen Analytics",
        "role": "customer",
        "plan": "pro",
        "betaTester": True,
        "region": "APAC",
        "accountAgeDays": 154,
        "deviceType": "mobile",
        "blurb": "Pro-plan beta tester. Matched by the same rule as Jordan — "
                 "one rule, many people, no code change.",
        "expected_variation": "spotlight",
        "expected_via": "RULE_MATCH",
    },
    "sam": {
        "key": "user-sam-okafor",
        "name": "Sam Okafor",
        "email": "sam.okafor@meridian.example",
        "title": "Director of Ops, Meridian Foods",
        "role": "customer",
        "plan": "enterprise",
        "betaTester": False,
        "region": "EMEA",
        "accountAgeDays": 1240,
        "deviceType": "desktop",
        "blurb": "Enterprise, but has NOT opted in to beta. The rule requires "
                 "both conditions, so this visitor still sees the control.",
        "expected_variation": "control",
        "expected_via": "FALLTHROUGH",
    },
    "riley": {
        "key": "user-riley-torres",
        "name": "Riley Torres",
        "email": "riley.torres@harborlight.example",
        "title": "Owner, Harborlight Supply",
        "role": "customer",
        "plan": "free",
        "betaTester": False,
        "region": "AMER",
        "accountAgeDays": 23,
        "deviceType": "mobile",
        "blurb": "A brand-new free-plan visitor — representative of almost all "
                 "40,000 daily visitors. Sees only what is fully released.",
        "expected_variation": "control",
        "expected_via": "FALLTHROUGH",
    },
}

DEFAULT_VISITOR_ID = "riley"

# The attributes shown as chips in the UI's targeting inspector, in order.
# These are exactly the attributes the README's targeting rule is built on.
INSPECTED_ATTRIBUTES = ("role", "plan", "betaTester", "region", "accountAgeDays", "deviceType")


def resolve_visitor_id(visitor_id: str | None) -> str:
    """Fall back to the default visitor for unknown or missing ids."""
    if visitor_id in VISITORS:
        return visitor_id
    return DEFAULT_VISITOR_ID


def build_context(visitor_id: str) -> Context:
    """Turn a demo visitor into a LaunchDarkly Context.

    The attributes set below are precisely what the LaunchDarkly rule builder
    will offer you when you write a targeting rule, e.g.

        plan       is one of   enterprise, pro
        betaTester is          true

    A note on `key`: it is the stable identifier LaunchDarkly uses for
    individual targeting and for consistent percentage rollouts. Use something
    durable (a user id), never something that changes between visits.
    """
    visitor = VISITORS[visitor_id]
    return (
        Context.builder(visitor["key"])
        .kind(CONTEXT_KIND)
        .name(visitor["name"])
        # `set()` adds a custom attribute. Custom attributes appear in the
        # LaunchDarkly rule builder's autocomplete once the SDK has evaluated a
        # flag for at least one context that carries them — so load the page
        # once before writing your rules and the names will be waiting for you.
        .set("email", visitor["email"])
        .set("role", visitor["role"])
        .set("plan", visitor["plan"])
        .set("betaTester", visitor["betaTester"])
        .set("region", visitor["region"])
        .set("accountAgeDays", visitor["accountAgeDays"])
        .set("deviceType", visitor["deviceType"])
        .build()
    )


def context_summary(visitor_id: str) -> dict:
    """The attribute name/value pairs the UI shows in its inspector."""
    visitor = VISITORS[visitor_id]
    return {name: visitor[name] for name in INSPECTED_ATTRIBUTES}
