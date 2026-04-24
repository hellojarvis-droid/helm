"""Canonical list of every integration Helm knows about.

This is the source of truth for:
  * The Connections page (`/connections`) — renders one card per entry
    with scope == 'account'
  * The per-business Integrations page (`/businesses/{id}/integrations`)
    — renders cards with scope == 'business'
  * The route layer when validating toolkit slugs
  * The provider adapters (lookups by slug)

Keep this list flat and well-typed; the web client pulls it verbatim
via GET /connectors/catalog and filters client-side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AuthMode = Literal["composio_oauth", "api_key"]
Scope = Literal["account", "business"]
Category = Literal[
    "Creative",
    "Commerce",
    "Payments",
    "Ads",
    "Social",
    "Ops",
    "Communication",
]


@dataclass(frozen=True, slots=True)
class Connector:
    slug: str
    name: str
    category: Category
    scope: Scope
    auth_mode: AuthMode
    description: str
    signup_url: str | None = None
    # A one-line hint shown in the connect modal: "Paste your API key from
    # Runway's dashboard — Settings → API." Leave empty for OAuth flows.
    connect_hint: str = ""
    # Rough popularity rank — fuels "most popular" sort on the page.
    popularity: int = 100
    # Optional short cost-hint: "~$0.50 / 10-second video render".
    cost_hint: str = ""

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "slug": self.slug,
            "name": self.name,
            "category": self.category,
            "scope": self.scope,
            "auth_mode": self.auth_mode,
            "description": self.description,
            "signup_url": self.signup_url,
            "connect_hint": self.connect_hint,
            "popularity": self.popularity,
            "cost_hint": self.cost_hint,
        }


CATALOG: tuple[Connector, ...] = (
    # ── Creative (account-wide) — Helm-managed ──────────────────────────
    # Runway, Higgsfield, Kling, Nano Banana, and Veo are NOT in the
    # user-facing catalog. Helm holds those provider accounts centrally
    # and users pay via credits — the render cost shows up as a
    # credit-balance debit (see services/credits.py). Existing user-
    # pasted keys in `account_integrations` continue to work for a
    # transitional period via env-first / vault-fallback resolution in
    # services/providers/base.py.
    Connector(
        slug="figma",
        name="Figma",
        category="Creative",
        scope="account",
        auth_mode="composio_oauth",
        description="Export brand assets + reference images into Creative Studio.",
        signup_url="https://figma.com/",
        popularity=60,
    ),
    # ── Communication (account-wide) ────────────────────────────────────
    Connector(
        slug="gmail",
        name="Gmail",
        category="Communication",
        scope="account",
        auth_mode="composio_oauth",
        description="Draft replies, send receipts, summarize your inbox.",
        signup_url="https://mail.google.com/",
        popularity=5,
    ),
    Connector(
        slug="slack",
        name="Slack",
        category="Communication",
        scope="account",
        auth_mode="composio_oauth",
        description="Post alerts, approvals, and digests to your Slack workspace.",
        signup_url="https://slack.com/",
        popularity=35,
    ),
    Connector(
        slug="notion",
        name="Notion",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Keep SOPs, specs, and meeting notes in sync.",
        signup_url="https://notion.so/",
        popularity=40,
    ),
    # ── Commerce (business-scoped) ──────────────────────────────────────
    Connector(
        slug="shopify",
        name="Shopify",
        category="Commerce",
        scope="business",
        auth_mode="composio_oauth",
        description="Storefront, products, orders — the canonical DTC spine.",
        signup_url="https://shopify.com/",
        popularity=5,
    ),
    Connector(
        slug="tiktok_shop",
        name="TikTok Shop",
        category="Commerce",
        scope="business",
        auth_mode="composio_oauth",
        description="In-feed commerce on TikTok — product feed and orders.",
        signup_url="https://seller-us.tiktok.com/",
        popularity=15,
    ),
    Connector(
        slug="amazon_seller",
        name="Amazon Seller Central",
        category="Commerce",
        scope="business",
        auth_mode="composio_oauth",
        description="List products, manage inventory, track Buy Box.",
        signup_url="https://sellercentral.amazon.com/",
        popularity=25,
    ),
    Connector(
        slug="etsy",
        name="Etsy",
        category="Commerce",
        scope="business",
        auth_mode="composio_oauth",
        description="Handmade / vintage marketplace with its own audience.",
        signup_url="https://etsy.com/sell",
        popularity=45,
    ),
    Connector(
        slug="printful",
        name="Printful",
        category="Commerce",
        scope="business",
        auth_mode="composio_oauth",
        description="Print-on-demand fulfillment for apparel + accessories.",
        signup_url="https://printful.com/",
        popularity=30,
    ),
    Connector(
        slug="cj_dropshipping",
        name="CJ Dropshipping",
        category="Commerce",
        scope="business",
        auth_mode="composio_oauth",
        description="Supplier + fulfillment for physical-product dropship.",
        signup_url="https://cjdropshipping.com/",
        popularity=50,
    ),
    # ── Ads (business-scoped) ───────────────────────────────────────────
    Connector(
        slug="meta_ads",
        name="Meta Ads",
        category="Ads",
        scope="business",
        auth_mode="composio_oauth",
        description="Campaigns across Instagram + Facebook with Advantage+.",
        signup_url="https://business.facebook.com/",
        popularity=5,
    ),
    Connector(
        slug="google_ads",
        name="Google Ads",
        category="Ads",
        scope="business",
        auth_mode="composio_oauth",
        description="Search + Performance Max campaigns with shared budget.",
        signup_url="https://ads.google.com/",
        popularity=10,
    ),
    Connector(
        slug="tiktok_ads",
        name="TikTok Ads",
        category="Ads",
        scope="business",
        auth_mode="composio_oauth",
        description="Smart+ campaigns with creative rotation.",
        signup_url="https://ads.tiktok.com/",
        popularity=20,
    ),
    Connector(
        slug="klaviyo",
        name="Klaviyo",
        category="Ads",
        scope="business",
        auth_mode="composio_oauth",
        description="Email + SMS flows with segmentation.",
        signup_url="https://klaviyo.com/",
        popularity=35,
    ),
    # ── Social (business-scoped) ────────────────────────────────────────
    Connector(
        slug="instagram",
        name="Instagram",
        category="Social",
        scope="business",
        auth_mode="composio_oauth",
        description="Reply to comments and DMs on the business profile.",
        signup_url="https://business.instagram.com/",
        popularity=10,
    ),
    Connector(
        slug="tiktok",
        name="TikTok",
        category="Social",
        scope="business",
        auth_mode="composio_oauth",
        description="Post content and respond to comments organically.",
        signup_url="https://tiktok.com/",
        popularity=15,
    ),
    Connector(
        slug="twitter",
        name="X (Twitter)",
        category="Social",
        scope="business",
        auth_mode="composio_oauth",
        description="Post updates and manage replies on the business handle.",
        signup_url="https://twitter.com/",
        popularity=40,
    ),
    Connector(
        slug="linkedin",
        name="LinkedIn",
        category="Social",
        scope="business",
        auth_mode="composio_oauth",
        description="Post to the business page; engage on founder content.",
        signup_url="https://linkedin.com/",
        popularity=55,
    ),
    Connector(
        slug="threads",
        name="Threads",
        category="Social",
        scope="business",
        auth_mode="composio_oauth",
        description="Post + reply on the Threads handle for the brand.",
        signup_url="https://threads.net/",
        popularity=65,
    ),
    Connector(
        slug="youtube",
        name="YouTube",
        category="Social",
        scope="business",
        auth_mode="composio_oauth",
        description="Upload shorts, reply to comments, track views.",
        signup_url="https://studio.youtube.com/",
        popularity=60,
    ),
    # ── Ops (business-scoped) ───────────────────────────────────────────
    Connector(
        slug="quickbooks",
        name="QuickBooks",
        category="Ops",
        scope="business",
        auth_mode="composio_oauth",
        description="Sync Stripe + Shopify data into bookkeeping automatically.",
        signup_url="https://quickbooks.intuit.com/",
        popularity=30,
    ),
    Connector(
        slug="xero",
        name="Xero",
        category="Ops",
        scope="business",
        auth_mode="composio_oauth",
        description="Alternative bookkeeping; popular outside the US.",
        signup_url="https://xero.com/",
        popularity=55,
    ),
    Connector(
        slug="gorgias",
        name="Gorgias",
        category="Ops",
        scope="business",
        auth_mode="composio_oauth",
        description="Customer-service ticketing with Shopify context.",
        signup_url="https://gorgias.com/",
        popularity=45,
    ),
    Connector(
        slug="intercom",
        name="Intercom",
        category="Ops",
        scope="business",
        auth_mode="composio_oauth",
        description="Live chat + help-center + tickets in one.",
        signup_url="https://intercom.com/",
        popularity=50,
    ),
    Connector(
        slug="namecheap",
        name="Namecheap",
        category="Ops",
        scope="business",
        auth_mode="api_key",
        description="Register domains for new ventures.",
        signup_url="https://namecheap.com/",
        connect_hint="Paste API key from Namecheap → Account → API Access.",
        popularity=70,
    ),
)

_BY_SLUG: dict[str, Connector] = {c.slug: c for c in CATALOG}


def get(slug: str) -> Connector | None:
    return _BY_SLUG.get(slug.lower().strip())


def all_connectors() -> tuple[Connector, ...]:
    return CATALOG


def filter_by_scope(scope: Scope) -> list[Connector]:
    return [c for c in CATALOG if c.scope == scope]
