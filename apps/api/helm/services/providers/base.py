"""Shared shape for Creative-Studio provider adapters.

Every adapter answers three questions:

  1. **start(mode, prompt, options, api_key) -> ProviderJob** — kick off a
     render on the provider's side; return the external job id + an
     (optional) early status hint.
  2. **poll(external_job_id, api_key) -> ProviderJob** — query status;
     return terminal result when available (output_url, thumbnail,
     actual cost if the provider reports it).
  3. **estimate_cost_cents(mode, options) -> int** — rough preview used
     before the user submits. We never charge this; it's display-only
     since keys are user-provided and the provider bills directly.

Key resolution is uniform: `get_api_key_for` looks up the
`account_integrations` row for the user + provider, decrypts the
ciphertext, and raises `ProviderKeyMissingError` if not configured. The
route layer converts that to a 503 with a "reconnect $provider" hint.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import AccountIntegration
from helm.services import integration_vault
from helm.services.integration_vault import ProviderKeyMissingError

# Creative-Studio providers Helm runs on its own accounts (users pay
# via credits). When the matching env key is set, adapters use it
# directly and the user's per-account pasted key (if any) is ignored.
_HELM_ENV_KEY_ATTR: dict[str, str] = {
    "runway": "runway_api_key",
    "higgsfield": "higgsfield_api_key",
    "kling": "kling_api_key",
    "nano_banana": "nano_banana_api_key",
    "veo": "veo_api_key",
    "ideogram": "ideogram_api_key",
    "flux": "flux_api_key",
    "midjourney": "midjourney_api_key",
    "sora": "openai_api_key",
    "cartesia": "cartesia_api_key",
    "suno": "suno_api_key",
    "stable_audio": "stability_api_key",
}

# Loose strings at the protocol boundary so adapters can hand through
# provider-native status values without layers of casts. The route layer
# validates `mode in {'image','video'}` + `status in (...terminal set)`
# against the DB check constraints — the safety net is at the edges.
RenderMode = str
JobStatus = str


@dataclass(frozen=True, slots=True)
class ProviderJob:
    external_job_id: str | None
    status: str  # queued | running | completed | failed
    output_url: str | None = None
    thumbnail_url: str | None = None
    cost_cents_actual: int | None = None
    error: str | None = None


class RenderProvider(Protocol):
    slug: str
    supports_image: bool
    supports_video: bool

    async def start(
        self, *, mode: str, prompt: str, options: dict[str, Any], api_key: str
    ) -> ProviderJob: ...

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob: ...

    def estimate_cost_cents(self, *, mode: str, options: dict[str, Any]) -> int: ...


_REGISTRY: dict[str, RenderProvider] = {}


def register(provider: RenderProvider) -> None:
    _REGISTRY[provider.slug] = provider


def lookup(slug: str) -> RenderProvider | None:
    return _REGISTRY.get(slug)


def helm_managed_slugs_with_keys() -> set[str]:
    """Provider slugs for which Helm has an env-managed API key loaded.

    Used by the shot worker to reroute shots whose chosen provider has
    no key configured — so a DAG that picked `veo` but `veo` isn't
    available falls back to, e.g., `runway`.
    """
    settings = get_settings()
    out: set[str] = set()
    for slug, attr in _HELM_ENV_KEY_ATTR.items():
        if getattr(settings, attr, "") or "":
            out.add(slug)
    return out


async def get_api_key_for(
    db: AsyncSession, *, user_id: uuid.UUID, provider_slug: str
) -> str:
    """Resolve the provider API key to use on this render.

    Resolution order:
      1. Helm env key (`HELM_{PROVIDER}_API_KEY`). When set, Helm pays
         the provider and the user is billed via credits.
      2. User-pasted key in `account_integrations` — transitional BYOK
         path. Kept working so existing users aren't stranded while
         Helm sets up its own provider accounts.
      3. ProviderKeyMissingError — route converts to 503 with a prompt
         to either contact support or wait for Helm-managed coverage.
    """
    attr = _HELM_ENV_KEY_ATTR.get(provider_slug)
    if attr:
        settings = get_settings()
        env_key: str = getattr(settings, attr, "") or ""
        if env_key:
            return env_key

    row_q = await db.execute(
        select(AccountIntegration).where(
            AccountIntegration.user_id == user_id,
            AccountIntegration.toolkit == provider_slug,
        )
    )
    row = row_q.scalar_one_or_none()
    if row is None or not row.api_key_ciphertext:
        raise ProviderKeyMissingError(provider_slug)
    key = integration_vault.decrypt_key(row.api_key_ciphertext)
    if not key:
        raise ProviderKeyMissingError(provider_slug)
    return key
