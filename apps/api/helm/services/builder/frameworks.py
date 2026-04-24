"""Framework detection + canonical dev/build commands.

The list is intentionally small. If detection fails we fall back to
`other` and the preview pane shows a helpful "preview unsupported"
state instead of a broken iframe.
"""

from __future__ import annotations

import json
from typing import Literal, TypedDict

Framework = Literal["next", "vite", "static", "react_cra", "other"]


class FrameworkInfo(TypedDict):
    framework: Framework
    dev_command: list[str]
    build_command: list[str]
    output_dir: str


_KNOWN: dict[Framework, FrameworkInfo] = {
    "next": {
        "framework": "next",
        "dev_command": ["npm", "run", "dev"],
        "build_command": ["npm", "run", "build"],
        "output_dir": ".next",
    },
    "vite": {
        "framework": "vite",
        "dev_command": ["npm", "run", "dev"],
        "build_command": ["npm", "run", "build"],
        "output_dir": "dist",
    },
    "react_cra": {
        "framework": "react_cra",
        "dev_command": ["npm", "start"],
        "build_command": ["npm", "run", "build"],
        "output_dir": "build",
    },
    "static": {
        "framework": "static",
        "dev_command": ["npx", "serve", "."],
        "build_command": [],
        "output_dir": ".",
    },
    "other": {
        "framework": "other",
        "dev_command": [],
        "build_command": [],
        "output_dir": "",
    },
}


def detect(files: dict[str, str]) -> FrameworkInfo:
    """Detect framework from file tree.

    `files` is {path -> text_content}. Binary files need not appear. We
    read package.json if present; fall back to static/other otherwise.
    """
    pkg_raw = files.get("package.json")
    if pkg_raw:
        try:
            pkg = json.loads(pkg_raw)
        except json.JSONDecodeError:
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "next" in deps:
            return _KNOWN["next"]
        # Broad match: any dep name containing "vite" (vite,
        # @vitejs/plugin-react, @vitejs/plugin-react-swc, vitest, etc.).
        if any("vite" in name for name in deps):
            return _KNOWN["vite"]
        if "react-scripts" in deps:
            return _KNOWN["react_cra"]
    if any(p == "index.html" or p.endswith("/index.html") for p in files):
        return _KNOWN["static"]
    return _KNOWN["other"]


def info(framework: Framework) -> FrameworkInfo:
    return _KNOWN[framework]
