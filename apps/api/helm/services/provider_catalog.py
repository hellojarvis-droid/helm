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
    # Simple Icons brand slug (https://simpleicons.org). When set, the web
    # client renders the real brand SVG via the Simple Icons CDN; missing or
    # unknown slugs fall back to the gradient-initial placeholder.
    icon_slug: str | None = None

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
            "icon_slug": self.icon_slug,
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
        icon_slug="figma",
    ),
    Connector(
        slug="canva",
        name="Canva",
        category="Creative",
        scope="account",
        auth_mode="composio_oauth",
        description="Pull brand kits and designs into Helm's Creative Studio.",
        signup_url="https://canva.com/",
        popularity=55,
        icon_slug="canva",
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
        icon_slug="gmail",
    ),
    Connector(
        slug="google_calendar",
        name="Google Calendar",
        category="Communication",
        scope="account",
        auth_mode="composio_oauth",
        description="Read your schedule; book meetings on your behalf.",
        signup_url="https://calendar.google.com/",
        popularity=8,
        icon_slug="googlecalendar",
    ),
    Connector(
        slug="google_drive",
        name="Google Drive",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Read briefs and reference docs; save reports back.",
        signup_url="https://drive.google.com/",
        popularity=12,
        icon_slug="googledrive",
    ),
    Connector(
        slug="outlook",
        name="Microsoft Outlook",
        category="Communication",
        scope="account",
        auth_mode="composio_oauth",
        description="Mail + calendar across your Microsoft 365 inbox.",
        signup_url="https://outlook.com/",
        popularity=22,
        icon_slug="microsoftoutlook",
    ),
    Connector(
        slug="onedrive",
        name="Microsoft OneDrive",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Files and folders shared across your Microsoft account.",
        signup_url="https://onedrive.live.com/",
        popularity=28,
        icon_slug="microsoftonedrive",
    ),
    Connector(
        slug="microsoft_teams",
        name="Microsoft Teams",
        category="Communication",
        scope="account",
        auth_mode="composio_oauth",
        description="Channel messages, meetings, and DMs.",
        signup_url="https://teams.microsoft.com/",
        popularity=32,
        icon_slug="microsoftteams",
    ),
    Connector(
        slug="sharepoint",
        name="SharePoint",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Org documents, lists, and site libraries.",
        signup_url="https://www.microsoft.com/microsoft-365/sharepoint/",
        popularity=42,
        icon_slug="microsoftsharepoint",
    ),
    Connector(
        slug="slack",
        name="Slack",
        category="Communication",
        scope="account",
        auth_mode="composio_oauth",
        description="Post alerts, approvals, and digests to your Slack workspace.",
        signup_url="https://slack.com/",
        popularity=18,
        icon_slug="slack",
    ),
    Connector(
        slug="dropbox",
        name="Dropbox",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Cloud file storage — read references, save outputs.",
        signup_url="https://dropbox.com/",
        popularity=46,
        icon_slug="dropbox",
    ),
    Connector(
        slug="box",
        name="Box",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Enterprise file storage and sharing.",
        signup_url="https://box.com/",
        popularity=58,
        icon_slug="box",
    ),
    # ── Ops (account-wide) ──────────────────────────────────────────────
    Connector(
        slug="notion",
        name="Notion",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Keep SOPs, specs, and meeting notes in sync.",
        signup_url="https://notion.so/",
        popularity=20,
        icon_slug="notion",
    ),
    Connector(
        slug="github",
        name="GitHub",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Repos, issues, and PRs — read context, open changes.",
        signup_url="https://github.com/",
        popularity=14,
        icon_slug="github",
    ),
    Connector(
        slug="linear",
        name="Linear",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Track tasks and issues across your projects.",
        signup_url="https://linear.app/",
        popularity=24,
        icon_slug="linear",
    ),
    Connector(
        slug="asana",
        name="Asana",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Project tasks and timelines for non-engineering work.",
        signup_url="https://asana.com/",
        popularity=44,
        icon_slug="asana",
    ),
    Connector(
        slug="jira",
        name="Jira",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Issue tracking across Atlassian projects.",
        signup_url="https://www.atlassian.com/software/jira",
        popularity=48,
        icon_slug="jira",
    ),
    Connector(
        slug="confluence",
        name="Confluence",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Internal wiki for SOPs, specs, and team docs.",
        signup_url="https://www.atlassian.com/software/confluence",
        popularity=68,
        icon_slug="confluence",
    ),
    Connector(
        slug="hubspot",
        name="HubSpot",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="CRM for contacts, deals, and pipelines.",
        signup_url="https://hubspot.com/",
        popularity=38,
        icon_slug="hubspot",
    ),
    Connector(
        slug="salesforce",
        name="Salesforce",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Enterprise CRM — contacts, accounts, opportunities.",
        signup_url="https://salesforce.com/",
        popularity=52,
        icon_slug="salesforce",
    ),
    Connector(
        slug="pipedrive",
        name="Pipedrive",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Sales pipeline CRM with deal tracking and activity logs.",
        signup_url="https://pipedrive.com/",
        popularity=62,
        icon_slug="pipedrive",
    ),
    Connector(
        slug="servicenow",
        name="ServiceNow",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="ITSM, incidents, and workflows for enterprise teams.",
        signup_url="https://servicenow.com/",
        popularity=72,
        icon_slug="servicenow",
    ),
    Connector(
        slug="stripe_data",
        name="Stripe (data)",
        category="Ops",
        scope="account",
        auth_mode="composio_oauth",
        description="Read customers, invoices, and payment data into Atlas. Helm's own Stripe Issuing card lives under Money — this is read-only context.",
        signup_url="https://stripe.com/",
        popularity=66,
        icon_slug="stripe",
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
        icon_slug="shopify",
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
        icon_slug="tiktok",
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
        icon_slug="amazon",
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
        icon_slug="etsy",
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
        icon_slug="printful",
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
        icon_slug="meta",
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
        icon_slug="googleads",
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
        icon_slug="tiktok",
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
        icon_slug="klaviyo",
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
        icon_slug="instagram",
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
        icon_slug="tiktok",
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
        icon_slug="x",
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
        icon_slug="linkedin",
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
        icon_slug="threads",
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
        icon_slug="youtube",
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
        icon_slug="quickbooks",
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
        icon_slug="xero",
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
        icon_slug="intercom",
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
        icon_slug="namecheap",
    ),
)

_BY_SLUG: dict[str, Connector] = {c.slug: c for c in CATALOG}


def get(slug: str) -> Connector | None:
    return _BY_SLUG.get(slug.lower().strip())


def all_connectors() -> tuple[Connector, ...]:
    return CATALOG


def filter_by_scope(scope: Scope) -> list[Connector]:
    return [c for c in CATALOG if c.scope == scope]
