"""Verify layer — static checks on touched files, plain-English report.

v1 runs lightweight checks:
  * JSON files must parse
  * TypeScript / JavaScript must have balanced braces + simple syntax check
  * HTML must be roughly well-formed (matching tags)

This is a safety net, not a full compiler. Deep tsc / eslint runs happen
in the browser WebContainer during preview. The goal here is to catch
obvious LLM mistakes (unclosed braces, broken JSON) before we hand
anything to the preview.
"""

from __future__ import annotations

import json
import re
from typing import TypedDict


class Check(TypedDict):
    name: str
    status: str  # ok | warn | fail
    plain_english: str
    detail: str | None


class VerifyReport(TypedDict):
    ok: bool
    checks: list[Check]
    warnings: int
    errors: int


async def run(*, files: dict[str, str], touched_paths: list[str]) -> VerifyReport:
    """Run checks on touched files only. Keep cheap + synchronous."""
    checks: list[Check] = []
    warnings = 0
    errors = 0
    for path in touched_paths:
        content = files.get(path)
        if content is None:
            continue
        if path.endswith(".json"):
            c = _check_json(path, content)
        elif path.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")):
            c = _check_js(path, content)
        elif path.endswith((".html", ".htm")):
            c = _check_html(path, content)
        else:
            continue
        checks.append(c)
        if c["status"] == "warn":
            warnings += 1
        elif c["status"] == "fail":
            errors += 1
    return {
        "ok": errors == 0,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def _check_json(path: str, content: str) -> Check:
    try:
        json.loads(content)
        return {
            "name": f"{path}: JSON valid",
            "status": "ok",
            "plain_english": f"{path} is valid JSON.",
            "detail": None,
        }
    except json.JSONDecodeError as e:
        return {
            "name": f"{path}: JSON invalid",
            "status": "fail",
            "plain_english": f"{path} has a JSON error — I'll need to fix that before preview.",
            "detail": str(e),
        }


def _check_js(path: str, content: str) -> Check:
    issues: list[str] = []
    opens = content.count("{")
    closes = content.count("}")
    if opens != closes:
        issues.append(f"{opens} '{{' vs {closes} '}}' — mismatched braces")
    opens_p = content.count("(")
    closes_p = content.count(")")
    if opens_p != closes_p:
        issues.append(f"{opens_p} '(' vs {closes_p} ')' — mismatched parens")
    # Flag stray `<<<<<<<` merge markers just in case.
    if re.search(r"^<{7}|^>{7}|^={7}", content, flags=re.MULTILINE):
        issues.append("merge-conflict markers found")
    if issues:
        return {
            "name": f"{path}: syntax sanity",
            "status": "fail",
            "plain_english": f"{path} has structural issues I should fix.",
            "detail": "; ".join(issues),
        }
    return {
        "name": f"{path}: syntax sanity",
        "status": "ok",
        "plain_english": f"{path} looks structurally sound.",
        "detail": None,
    }


def _check_html(path: str, content: str) -> Check:
    # Cheap balance check on a few common tags.
    problems: list[str] = []
    for tag in ("html", "body", "head", "div", "section", "main"):
        opens = len(re.findall(rf"<{tag}\b", content, flags=re.IGNORECASE))
        closes = len(re.findall(rf"</{tag}>", content, flags=re.IGNORECASE))
        if opens != closes:
            problems.append(f"<{tag}>: {opens} open / {closes} close")
    if problems:
        return {
            "name": f"{path}: HTML balance",
            "status": "warn",
            "plain_english": f"{path} has some unclosed tags — the preview might render oddly.",
            "detail": "; ".join(problems),
        }
    return {
        "name": f"{path}: HTML balance",
        "status": "ok",
        "plain_english": f"{path} looks balanced.",
        "detail": None,
    }
