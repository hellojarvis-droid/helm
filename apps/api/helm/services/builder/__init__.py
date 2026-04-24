"""Builder services.

Six internal layers, cleanly separated per SPEC.md:

    intent       — parse founder prompt → structured Intent
    plan         — intent + project context → Plan row (plain + technical)
    execute      — approved Plan → project-file writes
    verify       — syntax + lint + tsc; plain-English report
    explain      — user-facing summary of what changed
    versioning   — snapshot + load + one-step undo

An orchestrator glues them into `propose_plan` / `apply_plan`.

Keep each layer pure-ish: structured in, structured out, side effects
contained. Tests live under tests/services/builder/.
"""

from __future__ import annotations

from helm.services.builder import (
    execute,
    explain,
    frameworks,
    intent,
    orchestrator,
    plan,
    publisher,
    verify,
    versioning,
)

__all__ = [
    "execute",
    "explain",
    "frameworks",
    "intent",
    "orchestrator",
    "plan",
    "publisher",
    "verify",
    "versioning",
]
