#!/usr/bin/env python3
"""End-to-end smoke test against a running Helm API.

Run after a fresh deploy or whenever you want to confirm the money spine,
agent loop, and event log are wired together against a real environment.

Usage:

    HELM_API_BASE=https://api.helm.app \\
    HELM_JWT="$(supabase access-token)" \\
    uv run python scripts/seed-business.py

What it does:

1. GET /health              — confirms the API process is up
2. GET /ready               — confirms DB + integration config probe is green
3. POST /businesses         — creates a "Smoke Test Co" dtc_physical business
4. POST /chat               — sends "What should I do first?" to the CEO Agent;
                              streams the SSE response and prints the final text
5. GET /businesses/{id}/events  — confirms agent_events were written for the turn
6. PATCH /businesses/{id}   — flips the weekly cap to $0 (locks card)
7. (optional) DELETE         — does NOT delete the business; clean up by hand

Exits non-zero on the first failure with a one-line diagnosis.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any
from urllib import error, request

BASE = os.environ.get("HELM_API_BASE", "http://localhost:8000").rstrip("/")
JWT = os.environ.get("HELM_JWT", "")


def _req(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    stream: bool = False,
) -> tuple[int, str]:
    headers = {"Content-Type": "application/json"}
    if JWT:
        headers["Authorization"] = f"Bearer {JWT}"
    data = json.dumps(body).encode() if body else None
    req = request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=60) as resp:
            if stream:
                # SSE — read line-by-line until 'event: done' or EOF.
                chunks: list[str] = []
                for raw in resp:
                    line = raw.decode().rstrip("\n")
                    chunks.append(line)
                    if line == "event: done":
                        break
                return resp.status, "\n".join(chunks)
            return resp.status, resp.read().decode()
    except error.HTTPError as e:
        return e.code, e.read().decode()


def step(name: str) -> None:
    print(f"\n━━ {name}")


def die(msg: str) -> None:
    print(f"\n❌ {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not JWT:
        die("Set HELM_JWT to a Supabase user access token (anon or signed-in user).")

    step("1. /health")
    code, body = _req("GET", "/health")
    if code != 200:
        die(f"/health returned {code}: {body}")
    print(body)

    step("2. /ready")
    code, body = _req("GET", "/ready")
    if code != 200:
        die(f"/ready returned {code}: {body}")
    print(body)

    step("3. POST /businesses (create Smoke Test Co)")
    code, body = _req(
        "POST",
        "/businesses",
        {
            "name": f"Smoke Test Co {int(time.time())}",
            "vertical": "dtc_physical",
            "weekly_spend_cap_cents": 50_000,
        },
    )
    if code != 201:
        die(f"create business returned {code}: {body}")
    biz = json.loads(body)
    biz_id = biz["id"]
    print(f"created business {biz_id}")

    step("4. POST /chat (one turn)")
    code, sse = _req(
        "POST",
        "/chat",
        {"business_id": biz_id, "text": "What should I do first?"},
        stream=True,
    )
    if code != 200:
        die(f"/chat returned {code}: {sse[:500]}")
    # Pull text deltas out of the SSE stream just to prove streaming worked.
    text_chunks: list[str] = []
    for line in sse.splitlines():
        if line.startswith("data:"):
            try:
                payload = json.loads(line[5:].strip() or "{}")
            except json.JSONDecodeError:
                continue
            delta = payload.get("text") or payload.get("delta")
            if isinstance(delta, str):
                text_chunks.append(delta)
    response = "".join(text_chunks).strip()
    print(f"agent: {response[:240]}{'…' if len(response) > 240 else ''}")

    step("5. GET /businesses/{id}/events")
    code, body = _req("GET", f"/businesses/{biz_id}/events?limit=10")
    if code != 200:
        die(f"events returned {code}: {body}")
    events = json.loads(body)
    print(f"event log contains {len(events)} events for this business")
    if len(events) == 0:
        die("expected at least 1 event after the /chat turn")

    step("6. PATCH /businesses/{id} (lock card)")
    code, body = _req(
        "PATCH",
        f"/businesses/{biz_id}",
        {"weekly_spend_cap_cents": 0},
    )
    if code != 200:
        die(f"patch returned {code}: {body}")
    print("weekly cap set to $0 — Stripe Issuing card is now locked")

    print(
        f"\n✅ end-to-end ok. Inspect the business at {BASE.replace('api.', '')}"
        f"/businesses/{biz_id} (delete it manually when done)."
    )


if __name__ == "__main__":
    main()
