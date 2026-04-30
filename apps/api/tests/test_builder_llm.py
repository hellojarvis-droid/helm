from helm.services.builder._llm import _extract_json


def test_extract_json_does_not_return_inner_object_from_truncated_array() -> None:
    text = '[{"op":"write","path":"index.html","content":"full file"}'

    assert _extract_json(text) is None


def test_extract_json_prefers_outer_array_with_braces_inside_strings() -> None:
    text = (
        '```json\n'
        '[{"op":"write","path":"styles.css","content":"body { color: red; }"}]\n'
        "```"
    )

    parsed = _extract_json(text)

    assert isinstance(parsed, list)
    assert parsed[0]["path"] == "styles.css"
