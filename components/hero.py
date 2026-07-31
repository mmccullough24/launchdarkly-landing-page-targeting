"""The component being revamped: the ABC Company landing page hero.

This module holds ALL THREE versions of the hero side by side:

* `control()`    — the hero in production today. Known good. Boring on purpose.
* `spotlight()`  — the redesign: social proof and product metrics above the fold.
* `conversion()` — the boldest test: urgency, a trial offer, and a testimonial.

`build_hero(variation)` picks between them.

Nothing in this file knows that LaunchDarkly exists. The flag is evaluated once,
at the edge, in `app.py`, and the resulting variation name is handed down as a
plain string. That separation is deliberate and is the pattern worth copying:

* the component stays testable with no SDK, no network, and no account;
* when the revamp is finished you delete two functions and the flag, rather than
  unpicking SDK calls scattered through the view layer;
* a designer can iterate on `spotlight()` without ever touching flag code.

All copy and figures below are illustrative placeholder content for the demo.
"""

# Shared across every variation — the parts of the page that are not being
# tested. Keeping them here stops the variations drifting apart accidentally.
_PRODUCT_NAME = "ABC Operations Cloud"
_NAV = ("Product", "Solutions", "Pricing", "Docs", "Company")


def control() -> dict:
    """The hero currently served to production traffic.

    This is the safe default: it is what a brand-new visitor sees, what every
    visitor sees if the flag is turned off, and what everyone sees if
    LaunchDarkly is unreachable.
    """
    return {
        "variation": "control",
        "label": "Control — currently in production",
        "theme": "control",
        "eyebrow": None,
        "headline": "Operations software for growing teams",
        "subhead": (
            "ABC Operations Cloud brings orders, inventory, and fulfilment "
            "into one place."
        ),
        "primary_cta": "Request a demo",
        "secondary_cta": None,
        "bullets": [
            "Order and inventory management",
            "Fulfilment tracking",
            "Reporting and exports",
        ],
        "stats": [],
        "testimonial": None,
        "badge": None,
        "note": "The layout that has been converting steadily for eighteen months.",
    }


def spotlight() -> dict:
    """The redesign, released to a targeted audience first.

    Same offer, restructured: the value proposition leads, social proof and
    product metrics move above the fold, and the page offers a self-serve path
    alongside the sales path.
    """
    return {
        "variation": "spotlight",
        "label": "Spotlight — the redesign",
        "theme": "spotlight",
        "eyebrow": "Trusted by 2,400+ operations teams",
        "headline": "Ship orders faster, with fewer surprises",
        "subhead": (
            "See every order, shipment, and exception in one view — and catch "
            "the ones going wrong before your customers do."
        ),
        "primary_cta": "Start free trial",
        "secondary_cta": "Book a walkthrough",
        "bullets": [
            "Live exception alerts across every warehouse",
            "Forecasts that account for supplier lead time",
            "Connects to the tools you already run on",
        ],
        "stats": [
            {"value": "31%", "label": "fewer late shipments"},
            {"value": "4.2h", "label": "saved per ops lead each week"},
            {"value": "12 min", "label": "median setup time"},
        ],
        "testimonial": None,
        "badge": "New",
        "note": "Released to internal staff and opted-in customers first.",
    }


def conversion() -> dict:
    """The boldest test, reserved for named individuals.

    A more aggressive offer than the team is ready to put in front of paying
    customers. Individual targeting means it can run in production, against
    production data, seen only by the people who agreed to see it.
    """
    return {
        "variation": "conversion",
        "label": "Conversion — aggressive test",
        "theme": "conversion",
        "eyebrow": "Limited: onboarding included through Q3",
        "headline": "Your operations, under control in a week",
        "subhead": (
            "Start free, import your orders in an afternoon, and get a "
            "dedicated onboarding engineer for your first 30 days."
        ),
        "primary_cta": "Claim your free month",
        "secondary_cta": "Talk to sales",
        "bullets": [
            "No credit card, no procurement call",
            "Guided migration from spreadsheets or legacy ERP",
            "Cancel any time in one click",
        ],
        "stats": [
            {"value": "7 days", "label": "typical time to first value"},
            {"value": "$0", "label": "to start"},
        ],
        "testimonial": {
            "quote": (
                "We moved off spreadsheets in a weekend. The exception alerts "
                "alone paid for the year."
            ),
            "attribution": "Operations Lead, Northwind Trading",
        },
        "badge": "Experiment",
        "note": "Never shown to general traffic — individually targeted only.",
    }


# The registry `build_hero()` dispatches on. Adding a fourth variation to the
# landing page test means adding a function here and a variation in
# LaunchDarkly — no change to app.py.
_VARIATIONS = {
    "control": control,
    "spotlight": spotlight,
    "conversion": conversion,
}


def build_hero(variation: str) -> dict:
    """Return the view model for whichever hero the flag selected.

    `variation` comes straight from the LaunchDarkly evaluation in `app.py`.

    An unrecognised value falls back to the control rather than raising. That
    matters in production: if someone adds a fourth variation in the
    LaunchDarkly UI before this code knows about it, visitors get the
    known-good hero instead of a 500.
    """
    builder = _VARIATIONS.get(variation, control)
    view = builder()
    view["product_name"] = _PRODUCT_NAME
    view["nav"] = _NAV
    view["requested_variation"] = variation
    view["is_unknown_variation"] = variation not in _VARIATIONS
    return view
