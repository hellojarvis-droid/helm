"""Model registry — single source of truth for the Canvas Studio
model picker.

Each entry carries the three pills the picker shows (cost in credits,
typical latency in seconds, one-line best-for), plus the modalities
and whether it's the default "Recommended" choice for each modality.

`cost_credits` is an estimate so the UI can show a live pre-generate
number. Actual billing is still driven by real provider usage via
`services/credits.py` reserve → commit → refund.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Modality = Literal["image", "video", "edit", "enhance", "lipsync", "audio"]
Tool = Literal["image", "video", "edit", "enhance", "lipsync"]


@dataclass(frozen=True, slots=True)
class ModelEntry:
    slug: str
    name: str
    provider: str
    modalities: tuple[Modality, ...]
    cost_credits: int
    avg_seconds: int
    best_for: str
    description: str = ""
    recommended_for: tuple[Modality, ...] = ()
    helm_managed: bool = True
    deprecated: bool = False


# ── Image ────────────────────────────────────────────────────────────
_IMAGE_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry(
        slug="flux",
        name="Flux Pro 1.1",
        provider="flux",
        modalities=("image",),
        cost_credits=10,
        avg_seconds=8,
        best_for="Photoreal",
        description="Sharp, high-dynamic-range photorealism.",
        recommended_for=("image",),
    ),
    ModelEntry(
        slug="ideogram",
        name="Ideogram 2",
        provider="ideogram",
        modalities=("image",),
        cost_credits=8,
        avg_seconds=7,
        best_for="Typography",
        description="Best-in-class for images with readable in-image text.",
    ),
    ModelEntry(
        slug="midjourney",
        name="Midjourney v6",
        provider="midjourney",
        modalities=("image",),
        cost_credits=8,
        avg_seconds=30,
        best_for="Aesthetic",
        description="Painterly, stylized — strongest aesthetic signal.",
    ),
    ModelEntry(
        slug="nano_banana",
        name="Nano Banana",
        provider="nano_banana",
        modalities=("image",),
        cost_credits=2,
        avg_seconds=4,
        best_for="Fast stills",
        description="Fast single-image generation for inserts + cards.",
    ),
    ModelEntry(
        slug="runway",
        name="Runway gen4 image",
        provider="runway",
        modalities=("image", "video"),
        cost_credits=5,
        avg_seconds=6,
        best_for="Reliable all-purpose",
        description="Steady mid-complexity general-purpose image/video.",
    ),
)

# ── Video ────────────────────────────────────────────────────────────
_VIDEO_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry(
        slug="runway",
        name="Runway gen4 video",
        provider="runway",
        modalities=("video",),
        cost_credits=40,
        avg_seconds=90,
        best_for="All-purpose motion",
        description="Reliable text-to-video. Safe default.",
        recommended_for=("video",),
    ),
    ModelEntry(
        slug="veo",
        name="Veo 3",
        provider="veo",
        modalities=("video",),
        cost_credits=100,
        avg_seconds=120,
        best_for="Cinematic w/ audio",
        description="Motion-heavy scenes with people, dialogue sync, natural audio.",
    ),
    ModelEntry(
        slug="kling",
        name="Kling 2.5",
        provider="kling",
        modalities=("video",),
        cost_credits=60,
        avg_seconds=120,
        best_for="Stylized cinematic",
        description="Strong camera moves, stylized dream logic.",
    ),
    ModelEntry(
        slug="higgsfield",
        name="Higgsfield Soul",
        provider="higgsfield",
        modalities=("video",),
        cost_credits=40,
        avg_seconds=60,
        best_for="Product hero shots",
        description="Commercial-grade still-to-motion for product beats.",
    ),
    ModelEntry(
        slug="sora",
        name="Sora 2",
        provider="sora",
        modalities=("video",),
        cost_credits=150,
        avg_seconds=180,
        best_for="Complex physics",
        description="Long-range coherence, multi-character scenes.",
    ),
)

# ── Edit ─────────────────────────────────────────────────────────────
_EDIT_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry(
        slug="runway_edit",
        name="Runway Inpaint",
        provider="runway",
        modalities=("edit",),
        cost_credits=6,
        avg_seconds=10,
        best_for="Inpaint + mask",
        description="Paint a mask over any image and regenerate inside it.",
        recommended_for=("edit",),
    ),
    ModelEntry(
        slug="flux_edit",
        name="Flux Edit",
        provider="flux",
        modalities=("edit",),
        cost_credits=10,
        avg_seconds=12,
        best_for="Photoreal edits",
        description="Photoreal fill/replace with strong prompt adherence.",
    ),
)

# ── Enhance ──────────────────────────────────────────────────────────
_ENHANCE_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry(
        slug="runway_upscale",
        name="Runway Upscale",
        provider="runway",
        modalities=("enhance",),
        cost_credits=4,
        avg_seconds=8,
        best_for="4x upscale",
        description="Clean 4x resolution bump without hallucination.",
        recommended_for=("enhance",),
    ),
)

# ── Lipsync ──────────────────────────────────────────────────────────
_LIPSYNC_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry(
        slug="runway_lipsync",
        name="Runway Act",
        provider="runway",
        modalities=("lipsync",),
        cost_credits=20,
        avg_seconds=60,
        best_for="Face → audio sync",
        description="Drive any face from a voice track.",
        recommended_for=("lipsync",),
    ),
)

_ALL: tuple[ModelEntry, ...] = (
    *_IMAGE_MODELS,
    *_VIDEO_MODELS,
    *_EDIT_MODELS,
    *_ENHANCE_MODELS,
    *_LIPSYNC_MODELS,
)

# Build an id index keyed by (tool, slug) — same provider slug may
# appear under different tools with different defaults (Runway image
# vs Runway video).
_BY_TOOL_SLUG: dict[tuple[str, str], ModelEntry] = {}
for e in _ALL:
    for m in e.modalities:
        _BY_TOOL_SLUG[(m, e.slug)] = e


def all_models() -> list[ModelEntry]:
    return list(_ALL)


def for_tool(tool: Tool) -> list[ModelEntry]:
    return [e for e in _ALL if tool in e.modalities]


def get(tool: Tool, slug: str) -> ModelEntry | None:
    return _BY_TOOL_SLUG.get((tool, slug))


def recommended(tool: Tool) -> ModelEntry | None:
    for entry in for_tool(tool):
        if tool in entry.recommended_for:
            return entry
    tool_models = for_tool(tool)
    return tool_models[0] if tool_models else None


def estimate_cost_credits(
    *,
    tool: Tool,
    model: str,
    params: dict[str, object] | None = None,
) -> int:
    """Rough pre-gen cost shown live on the Generate button.

    Scales video by duration_seconds / 5 (the registry's base assumes a
    5-second video). Scales enhance by upscale factor (default 4x).
    """
    entry = get(tool, model)
    if entry is None:
        return 0
    base = entry.cost_credits
    params = params or {}
    if tool == "video":
        raw_seconds = params.get("duration_seconds", 5) or 5
        seconds = int(raw_seconds)  # type: ignore[call-overload]
        if seconds > 0:
            base = round(base * (seconds / 5.0))
    if tool == "enhance":
        raw_factor = params.get("upscale_factor", 4) or 4
        factor = int(raw_factor)  # type: ignore[call-overload]
        if factor > 4:
            base = round(base * (factor / 4.0))
    return max(1, base)


# ── Viral + camera-motion presets ────────────────────────────────────

# Hand-picked ~30 viral presets per the research doc — surfaced inside
# Image / Video tools as one-click preset chips, not separate "apps."
VIRAL_PRESETS: tuple[dict[str, object], ...] = (
    {"slug": "plushies", "label": "Plushies", "tool": "image", "prompt_suffix": ", plush toy, soft felt textures, kawaii"},
    {"slug": "micro_beasts", "label": "Micro Beasts", "tool": "image", "prompt_suffix": ", extreme macro, hyper-detailed creature"},
    {"slug": "outfit_swap", "label": "Outfit Swap", "tool": "image", "prompt_suffix": ", fashion editorial, different outfit"},
    {"slug": "product_packshot", "label": "Product Packshot", "tool": "image", "prompt_suffix": ", studio packshot, soft shadow, seamless background"},
    {"slug": "3d_figure", "label": "3D Figure", "tool": "image", "prompt_suffix": ", isometric 3D render, pastel, clay"},
    {"slug": "sticker", "label": "Sticker", "tool": "image", "prompt_suffix": ", die-cut sticker, bold outline, glossy vinyl"},
    {"slug": "pixel_game", "label": "Pixel Game", "tool": "image", "prompt_suffix": ", pixel art, 16-bit palette, retro game style"},
    {"slug": "polaroid", "label": "Polaroid", "tool": "image", "prompt_suffix": ", polaroid instant film, warm tone, slight vignette"},
    {"slug": "1990s_ad", "label": "1990s Ad", "tool": "image", "prompt_suffix": ", 90s magazine ad, muted color, grainy"},
    {"slug": "architectural", "label": "Architectural", "tool": "image", "prompt_suffix": ", architectural photography, clean geometry"},
    {"slug": "bullet_time", "label": "Bullet Time", "tool": "video", "prompt_suffix": ", 360-degree camera orbit, time frozen around subject"},
    {"slug": "crash_zoom", "label": "Crash Zoom", "tool": "video", "prompt_suffix": ", rapid crash-zoom in on subject's face"},
    {"slug": "super_dolly", "label": "Super Dolly", "tool": "video", "prompt_suffix": ", fast dolly push-in, low angle, dramatic"},
    {"slug": "fpv_drone", "label": "FPV Drone", "tool": "video", "prompt_suffix": ", FPV drone pass through scene, smooth fast motion"},
    {"slug": "robo_arm", "label": "Robo-Arm", "tool": "video", "prompt_suffix": ", industrial robo-arm camera move, precise arc"},
    {"slug": "slow_push", "label": "Slow Push", "tool": "video", "prompt_suffix": ", slow cinematic push-in, 24fps, tripod feel"},
    {"slug": "handheld", "label": "Handheld", "tool": "video", "prompt_suffix": ", handheld documentary shake, natural breath"},
    {"slug": "tilt_shift", "label": "Tilt Shift", "tool": "video", "prompt_suffix": ", tilt-shift miniature effect, shallow focus band"},
    {"slug": "3d_rotation", "label": "3D Rotation", "tool": "video", "prompt_suffix": ", slow orbit around centered subject"},
    {"slug": "time_freeze", "label": "Time Freeze", "tool": "video", "prompt_suffix": ", everything pauses except hero element"},
    {"slug": "product_pour", "label": "Product Pour", "tool": "video", "prompt_suffix": ", liquid pour around product, splash choreography"},
    {"slug": "unboxing", "label": "Unboxing", "tool": "video", "prompt_suffix": ", overhead unboxing reveal, soft diffused light"},
    {"slug": "parallax_dolly", "label": "Parallax Dolly", "tool": "video", "prompt_suffix": ", lateral dolly with deep foreground/background parallax"},
)

# Camera-motion presets — explicit control chips on Video tool.
# Aligned with Higgsfield's cited "moat" (bullet time, crash zoom, etc.)
# so we offer the same chips but as prompts on top of any video model.
CAMERA_MOTION_PRESETS: tuple[dict[str, str], ...] = (
    {"slug": "static", "label": "Static tripod", "prompt_suffix": ", static tripod shot"},
    {"slug": "slow_push", "label": "Slow push-in", "prompt_suffix": ", slow cinematic push-in"},
    {"slug": "crash_zoom", "label": "Crash zoom", "prompt_suffix": ", rapid crash zoom"},
    {"slug": "orbit", "label": "Orbit", "prompt_suffix": ", slow orbit around subject"},
    {"slug": "bullet_time", "label": "Bullet time", "prompt_suffix": ", 360 bullet-time freeze"},
    {"slug": "fpv", "label": "FPV drone", "prompt_suffix": ", FPV drone pass-through"},
    {"slug": "dolly_zoom", "label": "Dolly zoom", "prompt_suffix": ", Hitchcock dolly zoom"},
    {"slug": "robo_arm", "label": "Robo-arm", "prompt_suffix": ", industrial robo-arm arc"},
    {"slug": "handheld", "label": "Handheld", "prompt_suffix": ", handheld doc shake"},
    {"slug": "whip_pan", "label": "Whip pan", "prompt_suffix": ", whip pan transition"},
    {"slug": "tilt_up", "label": "Tilt up", "prompt_suffix": ", dramatic tilt-up reveal"},
    {"slug": "pullback_reveal", "label": "Pullback reveal", "prompt_suffix": ", slow pullback wide reveal"},
)
