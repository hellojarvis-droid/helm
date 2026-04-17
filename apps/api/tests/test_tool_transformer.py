"""Tool→ToolParam transformer — unit tests.

Covers both Pydantic-model Tool objects (the shape `client.tools.get` returns)
and plain dicts (what might appear when we accept cached / serialized tools).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from helm.services.composio_client import tools_as_anthropic_params


@dataclass
class _FakeTool:
    """Shape mirrors composio.types.Tool's essential fields."""

    slug: str
    description: str
    input_parameters: dict[str, Any]
    human_description: str | None = None


def test_converts_tool_objects_to_anthropic_param_shape() -> None:
    tools = [
        _FakeTool(
            slug="GMAIL_SEND_EMAIL",
            description="Send an email through Gmail.",
            input_parameters={
                "type": "object",
                "properties": {"to": {"type": "string"}, "subject": {"type": "string"}},
                "required": ["to", "subject"],
            },
        )
    ]
    params = tools_as_anthropic_params(tools)
    assert len(params) == 1
    p = params[0]
    assert p["name"] == "GMAIL_SEND_EMAIL"
    assert p["description"] == "Send an email through Gmail."
    assert p["input_schema"]["required"] == ["to", "subject"]


def test_accepts_plain_dicts_with_the_same_shape() -> None:
    tools = [
        {
            "slug": "SHOPIFY_LIST_PRODUCTS",
            "description": "List products in a shop.",
            "input_parameters": {"type": "object", "properties": {}},
        }
    ]
    params = tools_as_anthropic_params(tools)
    assert params[0]["name"] == "SHOPIFY_LIST_PRODUCTS"
    assert params[0]["description"] == "List products in a shop."


def test_falls_back_to_human_description_when_description_missing() -> None:
    tools = [
        _FakeTool(
            slug="SLUG",
            description="",
            input_parameters={"type": "object", "properties": {}},
            human_description="Humane description here.",
        )
    ]
    params = tools_as_anthropic_params(tools)
    assert params[0]["description"] == "Humane description here."


def test_skips_tools_without_a_slug() -> None:
    tools = [_FakeTool(slug="", description="x", input_parameters={"type": "object"})]
    assert tools_as_anthropic_params(tools) == []


def test_supplies_default_empty_schema_when_input_parameters_is_missing() -> None:
    tools = [{"slug": "FOO", "description": "bar"}]
    params = tools_as_anthropic_params(tools)
    assert params[0]["input_schema"] == {"type": "object", "properties": {}}
