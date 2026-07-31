"""The people who use ABC Company's dashboard.

A LaunchDarkly *context* describes who (or what) a flag is being evaluated for.
Every attribute you set here becomes something you can target on in the
LaunchDarkly UI without changing or redeploying this code — which is what makes
"test in production" possible: you release the new code to internal staff only,
then widen the audience once you trust it.

The demo ships three fixed personas so you can switch between them in the
browser and watch one flag serve different values to different people.
"""

from ldclient import Context

PERSONAS = {
    "avery": {
        "key": "user-avery-chen",
        "name": "Avery Chen",
        "email": "avery.chen@abccompany.example",
        "title": "QA Engineer, ABC Company",
        "role": "internal-qa",  # target on this to test in production
        "betaTester": True,
        "plan": "internal",
        "blurb": "Internal staff. The first person who should see new code in production.",
    },
    "jordan": {
        "key": "user-jordan-blake",
        "name": "Jordan Blake",
        "email": "jordan.blake@northwind.example",
        "title": "Operations Lead, Northwind Trading",
        "role": "customer",
        "betaTester": True,  # opted in to the early-access program
        "plan": "enterprise",
        "blurb": "Enterprise customer who opted in to early access.",
    },
    "riley": {
        "key": "user-riley-torres",
        "name": "Riley Torres",
        "email": "riley.torres@harborlight.example",
        "title": "Founder, Harborlight Supply",
        "role": "customer",
        "betaTester": False,
        "plan": "pro",
        "blurb": "General availability customer. Should only see fully released features.",
    },
}

DEFAULT_PERSONA_ID = "riley"


def resolve_persona_id(persona_id: str | None) -> str:
    """Fall back to the default persona for unknown/missing ids."""
    if persona_id in PERSONAS:
        return persona_id
    return DEFAULT_PERSONA_ID


def build_context(persona_id: str) -> Context:
    """Turn a persona into a LaunchDarkly Context.

    The attributes below are exactly what you can build targeting rules on in
    the LaunchDarkly UI, e.g. "betaTester is true -> serve true".
    """
    persona = PERSONAS[persona_id]
    return (
        Context.builder(persona["key"])
        .kind("user")
        .name(persona["name"])
        # `set` adds a custom attribute. Custom attributes show up in the
        # LaunchDarkly targeting rule builder once the SDK has evaluated a flag
        # for a context that includes them.
        .set("email", persona["email"])
        .set("role", persona["role"])
        .set("betaTester", persona["betaTester"])
        .set("plan", persona["plan"])
        .build()
    )
