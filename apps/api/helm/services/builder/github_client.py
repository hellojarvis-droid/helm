"""GitHub import/export for Builder.

v1 scope:
- Public GitHub repos import via tarball fetch (no auth). Parses the
  tarball in-memory; text files load into BuilderProjectFile, binaries
  get dropped in v1 (future: persist to Supabase Storage).
- Export to ZIP is just a server-side archive build over the current
  version's files.
- Push-commit to GitHub lives behind the user's Composio OAuth token,
  wired in the next pass — the route is there as a stub that returns
  202 with a clear "connect GitHub" response until auth is live.

Keep this module offline-friendly: any network call is wrapped in
try/except and surfaces a clear error upstream rather than 500-ing.
"""

from __future__ import annotations

import io
import re
import tarfile
import zipfile
from typing import TypedDict
from urllib.parse import urlparse

import httpx


class GitHubImportError(Exception):
    """Tarball fetch or unpack failed. Routes convert to 4xx."""


class GitHubRef(TypedDict):
    owner: str
    repo: str
    ref: str  # branch or sha; defaults to HEAD


_REPO_URL = re.compile(
    r"^(?:https?://)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def parse_repo_url(url: str) -> GitHubRef:
    """Accept `https://github.com/{owner}/{repo}` or `github.com/{owner}/{repo}`.
    Raises on anything else."""
    s = url.strip().rstrip("/")
    parsed = urlparse(s if "://" in s else f"https://{s}")
    host = (parsed.hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        raise GitHubImportError(
            f"Only github.com URLs are supported for import (got {host or 'empty'})."
        )
    path = (parsed.path or "").strip("/")
    m = _REPO_URL.match(f"github.com/{path}")
    if not m:
        raise GitHubImportError(
            "URL must look like https://github.com/owner/repo."
        )
    return {"owner": m.group("owner"), "repo": m.group("repo"), "ref": "HEAD"}


# Don't pull binaries or bloated junk on import. Text files only, sized.
_MAX_FILE_BYTES = 512_000  # 500KB per file cap
_MAX_TOTAL_BYTES = 8_000_000  # 8MB whole-project cap
_MAX_FILE_COUNT = 2000
_BINARY_EXT = {
    "png", "jpg", "jpeg", "gif", "webp", "ico", "bmp",
    "mp3", "mp4", "mov", "wav", "ogg", "webm",
    "zip", "gz", "tgz", "tar",
    "woff", "woff2", "ttf", "otf",
    "pdf",
    "exe", "dll", "so", "dylib",
}
_SKIP_DIRS = {
    "node_modules", ".git", ".next", "dist", "build", ".vite",
    ".cache", ".turbo", "coverage", ".venv", "__pycache__",
}


async def fetch_public_repo_files(
    owner: str, repo: str, ref: str = "HEAD"
) -> dict[str, str]:
    """Download a public repo's tarball and return {path -> text content}.

    Skips binaries, lockfile junk, and any dir in `_SKIP_DIRS`. If the
    repo is private or missing, GitHub returns 404/302 and we raise
    a plain-English error.
    """
    url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/{ref}"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code == 404:
        raise GitHubImportError(
            f"Couldn't find {owner}/{repo}. If it's private, GitHub connection is required (coming soon)."
        )
    if resp.status_code >= 400:
        raise GitHubImportError(
            f"GitHub returned {resp.status_code}; try again or check the URL."
        )
    return _unpack_tarball(resp.content)


def _unpack_tarball(data: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                if len(out) >= _MAX_FILE_COUNT:
                    break
                path = _strip_tar_prefix(member.name)
                if _should_skip(path):
                    continue
                if member.size > _MAX_FILE_BYTES:
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                try:
                    text = f.read().decode("utf-8")
                except UnicodeDecodeError:
                    continue  # non-utf8 treated as binary; skip
                total += len(text)
                if total > _MAX_TOTAL_BYTES:
                    break
                out[path] = text
    except tarfile.TarError as e:
        raise GitHubImportError(f"Couldn't unpack the repo: {e}") from e
    if not out:
        raise GitHubImportError(
            "The repo didn't have any text files I could read. Is it empty?"
        )
    return out


def _strip_tar_prefix(name: str) -> str:
    # GitHub tarballs prefix paths with `{repo}-{sha}/`. Drop it.
    parts = name.split("/", 1)
    return parts[1] if len(parts) == 2 else parts[0]


def _should_skip(path: str) -> bool:
    if not path or path.endswith("/"):
        return True
    segments = path.split("/")
    if any(seg in _SKIP_DIRS for seg in segments):
        return True
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in _BINARY_EXT:
        return True
    # Lockfiles are noisy and rarely user-edited by founders.
    basename = segments[-1]
    return basename in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}


def unpack_zip(data: bytes) -> dict[str, str]:
    """Same rules as `_unpack_tarball` but for a user-uploaded ZIP."""
    out: dict[str, str] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if len(out) >= _MAX_FILE_COUNT:
                    break
                path = _strip_zip_prefix(info.filename)
                if _should_skip(path):
                    continue
                if info.file_size > _MAX_FILE_BYTES:
                    continue
                try:
                    text = zf.read(info).decode("utf-8")
                except UnicodeDecodeError:
                    continue
                total += len(text)
                if total > _MAX_TOTAL_BYTES:
                    break
                out[path] = text
    except zipfile.BadZipFile as e:
        raise GitHubImportError(f"Couldn't read the ZIP: {e}") from e
    if not out:
        raise GitHubImportError(
            "The ZIP didn't have any text files I could read. Is it empty?"
        )
    return out


def _strip_zip_prefix(name: str) -> str:
    # Most ZIP exports wrap contents in a top-level dir. Peel one.
    parts = name.split("/", 1)
    return parts[1] if len(parts) == 2 and parts[1] else parts[0]


def build_export_zip(files: dict[str, str]) -> bytes:
    """Build an in-memory ZIP of the project's current file tree."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()
