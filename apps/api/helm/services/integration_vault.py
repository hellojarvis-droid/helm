"""Encrypted at-rest storage for user-provided provider API keys.

Keys live in `integrations.api_key_ciphertext` (per-business) or
`account_integrations.api_key_ciphertext` (per-user) as Fernet tokens
(ASCII base64). The Fernet key is `HELM_INTEGRATION_SECRET` — rotate it
and all existing ciphertext becomes unreadable, so treat it like a DB
password.

**Billing model: bring-your-own-keys.** Helm never holds provider
accounts on behalf of users. The user's Runway / Higgsfield / etc.
account is billed directly by those providers; Helm is just an
orchestrator. We show an estimated cost per operation in the UI for
transparency but never meter or front spend.

Fail-closed invariants:

    * `encrypt_key` without HELM_INTEGRATION_SECRET set raises. We would
      rather refuse to save than write plaintext to disk.
    * `decrypt_key` returns None on invalid ciphertext; callers treat
      that as "no key available" — adapter then raises ProviderKeyMissing
      and the route converts to 503 so the UI can prompt for reconnect.
"""

from __future__ import annotations

import structlog
from cryptography.fernet import Fernet, InvalidToken

from helm.config import get_settings

log = structlog.get_logger("helm.vault")


class ProviderKeyMissingError(Exception):
    """Raised when no user-provided key exists for a provider.

    Route handlers convert this to 503 + "reconnect $provider" so the UI
    can prompt the user to add/refresh their key.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider}: no user-provided key on file. Have the user paste "
            "their key via the Connections page."
        )
        self.provider = provider


class IntegrationSecretMissingError(RuntimeError):
    """Raised when HELM_INTEGRATION_SECRET isn't configured but encrypt is called.

    We refuse to fall back to plaintext — losing ciphertext after a deploy is
    recoverable; leaking plaintext API keys is not.
    """


def _fernet() -> Fernet | None:
    """Return a Fernet instance, or None if the secret isn't configured."""
    secret = get_settings().integration_secret
    if not secret:
        return None
    return Fernet(secret.encode() if isinstance(secret, str) else secret)


def encrypt_key(plaintext: str) -> str:
    """Fernet-encrypt a user-provided API key. Returns the token as ASCII text."""
    if not plaintext:
        raise ValueError("cannot encrypt empty api key")
    f = _fernet()
    if f is None:
        raise IntegrationSecretMissingError(
            "HELM_INTEGRATION_SECRET is not set; cannot store user-provided api keys"
        )
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_key(ciphertext: str | None) -> str | None:
    """Decrypt a stored ciphertext. Returns None on missing input, invalid
    token, or missing secret — callers treat that as "no key available"
    and raise ProviderKeyMissingError so the UI can prompt for reconnect."""
    if not ciphertext:
        return None
    f = _fernet()
    if f is None:
        log.warning("vault.decrypt_skipped", reason="no_integration_secret")
        return None
    try:
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        log.warning("vault.decrypt_failed", reason="invalid_token")
        return None


def mask_key(plaintext: str | None) -> str:
    """Return a display-safe masked view of a key. Show only the last 4 chars."""
    if not plaintext or len(plaintext) < 6:
        return "•" * 8
    return "•" * 6 + plaintext[-4:]
