"""Creative Studio provider adapters.

Each adapter implements `RenderProvider`: start an image or video job,
poll its status, and return a rough cost estimate for display in the UI
before the user commits. Adapters call providers with the user's key
(resolved via `get_api_key_for`), never Helm's — Creative Studio is
strictly bring-your-own-keys per helm_product_decisions.
"""

from __future__ import annotations

from helm.services.providers.base import (
    ProviderJob,
    RenderProvider,
    get_api_key_for,
    helm_managed_slugs_with_keys,
    lookup,
    register,
)
from helm.services.providers.cartesia import CARTESIA
from helm.services.providers.flux import FLUX
from helm.services.providers.higgsfield import HIGGSFIELD
from helm.services.providers.ideogram import IDEOGRAM
from helm.services.providers.kling import KLING
from helm.services.providers.midjourney import MIDJOURNEY
from helm.services.providers.nano_banana import NANO_BANANA
from helm.services.providers.runway import RUNWAY
from helm.services.providers.sora import SORA
from helm.services.providers.stable_audio import STABLE_AUDIO
from helm.services.providers.suno import SUNO
from helm.services.providers.veo import VEO

# Register on import so lookup(slug) finds them.
register(RUNWAY)
register(HIGGSFIELD)
register(KLING)
register(NANO_BANANA)
register(VEO)
register(IDEOGRAM)
register(FLUX)
register(MIDJOURNEY)
register(SORA)
register(CARTESIA)
register(SUNO)
register(STABLE_AUDIO)

__all__ = [
    "CARTESIA",
    "FLUX",
    "HIGGSFIELD",
    "IDEOGRAM",
    "KLING",
    "MIDJOURNEY",
    "NANO_BANANA",
    "RUNWAY",
    "SORA",
    "STABLE_AUDIO",
    "SUNO",
    "VEO",
    "ProviderJob",
    "RenderProvider",
    "get_api_key_for",
    "helm_managed_slugs_with_keys",
    "lookup",
    "register",
]
