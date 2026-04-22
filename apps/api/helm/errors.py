"""User-facing error helpers.

The API never leaks raw exception text to clients. Domain code raises a
`ClientError` (or is caught by the global handler in `main.py`), which
serializes to a structured `detail` payload:

    {"error": "<code>", "message": "<user-facing sentence>", "trace_id": "<id>"}

Clients parse `detail.error` for branch logic and surface `detail.message`
directly to the user. Extra fields (e.g. `needed_cents`) ride alongside.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ClientError(HTTPException):
    """HTTPException with a structured, user-safe body.

    Raise this instead of `HTTPException(detail=str(exc))`. The message must
    read like a sentence we'd show to a non-technical user — no stack traces,
    no error codes, no Python-isms.
    """

    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        detail: dict[str, Any] = {"error": code, "message": message}
        if extra:
            detail.update(extra)
        super().__init__(status_code=status_code, detail=detail)


# Common canned responses for the recurring shapes so call sites read well.


def upstream_unavailable(service: str) -> ClientError:
    """A downstream service (Stripe, Composio, a scraper, etc.) failed."""
    return ClientError(
        "upstream_unavailable",
        status_code=502,
        message=(
            f"{service} is temporarily unavailable. Try again in a moment — "
            "we've logged it on our side."
        ),
        extra={"service": service},
    )


def invalid_input(message: str, *, code: str = "invalid_input") -> ClientError:
    return ClientError(code, status_code=400, message=message)


def conflict(message: str, *, code: str = "conflict") -> ClientError:
    return ClientError(code, status_code=409, message=message)


def unprocessable(message: str, *, code: str = "unprocessable") -> ClientError:
    return ClientError(code, status_code=422, message=message)
