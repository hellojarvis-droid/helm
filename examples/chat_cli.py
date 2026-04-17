"""chat_cli.py — talk to your own deployed Helm API from the terminal.

Usage:
    export HELM_API_BASE=http://localhost:8000
    export HELM_JWT="<supabase access_token from signed-in session>"
    uv run --project apps/api python examples/chat_cli.py

The JWT comes from any Supabase sign-in (web, the helm-gen-test-jwt.py helper,
or a CLI session). The CLI streams SSE events and prints text as it arrives.
"""

from __future__ import annotations

import json
import os
import sys

import httpx

API_BASE = os.environ.get("HELM_API_BASE", "http://localhost:8000").rstrip("/")
JWT = os.environ.get("HELM_JWT", "")


def main() -> int:
    if not JWT:
        print(
            "error: set HELM_JWT to a valid Supabase access token (JWT).\n"
            "       Tip: signed-in session in the Supabase dashboard exposes it,\n"
            "       or use the helper in examples/helm-gen-test-jwt.py (lands later).",
            file=sys.stderr,
        )
        return 2

    print(f"helm chat → {API_BASE}  (Ctrl-C to exit)")
    print()

    while True:
        try:
            user_msg = input("you ❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user_msg:
            continue
        if user_msg in {"exit", "quit", ":q"}:
            return 0

        _send_turn(user_msg)
        print()


def _send_turn(message: str) -> None:
    headers = {
        "Authorization": f"Bearer {JWT}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {"message": message}

    print("helm ❯ ", end="", flush=True)
    try:
        with httpx.stream(
            "POST", f"{API_BASE}/chat", headers=headers, json=payload, timeout=120
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload_json = line[len("data: ") :]
                try:
                    event = json.loads(payload_json)
                except json.JSONDecodeError:
                    continue
                _render_event(event)
    except httpx.HTTPStatusError as e:
        print(f"\n! HTTP {e.response.status_code}: {e.response.text[:200]}")
    except httpx.HTTPError as e:
        print(f"\n! network error: {e}")


def _render_event(event: dict) -> None:
    kind = event.get("kind")
    if kind == "user_logged":
        return  # we already echoed what the user typed
    if kind == "text_delta":
        print(event.get("text", ""), end="", flush=True)
        return
    if kind == "tool_call":
        print(f"\n   [tool] {event.get('name')}({_compact(event.get('input'))})", flush=True)
        return
    if kind == "tool_result":
        label = "error" if event.get("is_error") else "ok"
        print(f"   [tool←] {event.get('name')}: {label}", flush=True)
        return
    if kind == "approval_requested":
        print(
            f"\n   [approval] {event.get('approval_kind')}: {event.get('summary')}",
            flush=True,
        )
        print(f"              id={event.get('approval_id')}", flush=True)
        return
    if kind == "turn_cost":
        print(
            f"\n   ({event.get('input_tokens', 0)} in / "
            f"{event.get('output_tokens', 0)} out / "
            f"{event.get('cost_cents', 0)}¢)",
            flush=True,
        )
        return
    if kind == "done":
        return
    if kind == "error":
        print(f"\n! {event.get('reason')} {event.get('detail', '')}")
        return


def _compact(obj) -> str:
    if obj is None:
        return ""
    s = json.dumps(obj, separators=(",", ":"))
    return s if len(s) < 80 else s[:77] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
