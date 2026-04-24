"""Starter templates for blank projects.

We keep a small number of hand-rolled templates inline (as dict[path,
content]) rather than shipping scaffolding binaries. A founder picking
"blank" gets a minimal Vite + React site with Tailwind-style warm
palette so the first edit isn't a wall of raw HTML.

To add a template, append a new function and register it in
`TEMPLATES`. Each template returns {path -> content}.
"""

from __future__ import annotations

from collections.abc import Callable


def _vite_react_landing() -> dict[str, str]:
    return {
        "package.json": """{
  "name": "helm-builder-project",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.3.0"
  }
}
""",
        "vite.config.js": """import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Don't force host/port — WebContainer intercepts the default
// localhost binding; `host: true` (=0.0.0.0) prevents the port from
// being proxied and the preview never receives `server-ready`.
export default defineConfig({
  plugins: [react()],
});
""",
        "index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Your new site</title>
    <link rel="stylesheet" href="/src/styles.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
""",
        "src/main.jsx": """import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";

createRoot(document.getElementById("root")).render(<App />);
""",
        "src/App.jsx": """export function App() {
  return (
    <main>
      <section className="hero">
        <h1>A beautiful new idea</h1>
        <p>Describe what you want in plain English. Builder takes it from here.</p>
        <a className="cta" href="#contact">Get started</a>
      </section>
      <section id="contact" className="contact">
        <h2>Stay in touch</h2>
        <p>hello@example.com</p>
      </section>
    </main>
  );
}
""",
        "src/styles.css": """:root {
  --paper: #faf7f2;
  --ink: #1a1714;
  --terracotta: #b7603b;
  --sand: #efe9de;
  --rule: #e6dfd1;
  color-scheme: light;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: var(--paper); color: var(--ink); }
main { max-width: 900px; margin: 0 auto; padding: 4rem 2rem; }
.hero h1 { font-size: 3rem; line-height: 1.05; margin: 0 0 1rem; }
.hero p { font-size: 1.125rem; color: #4b4541; margin: 0 0 2rem; }
.cta {
  display: inline-block; padding: 0.75rem 1.25rem; background: var(--ink);
  color: var(--paper); border-radius: 4px; text-decoration: none;
  transition: background 0.15s;
}
.cta:hover { background: var(--terracotta); }
.contact { margin-top: 4rem; padding-top: 2rem; border-top: 1px solid var(--rule); }
""",
        "README.md": """# Your new site

Built with Helm Builder. Describe a change and Builder will apply it.
""",
        ".gitignore": """node_modules
dist
.vite
""",
    }


def _static_landing() -> dict[str, str]:
    return {
        "index.html": """<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Your new site</title>
<style>
:root { --paper: #faf7f2; --ink: #1a1714; --terracotta: #b7603b; }
body { margin: 0; font-family: system-ui, sans-serif; background: var(--paper); color: var(--ink); }
main { max-width: 900px; margin: 0 auto; padding: 4rem 2rem; }
h1 { font-size: 3rem; margin: 0 0 1rem; }
p { font-size: 1.125rem; color: #4b4541; }
a { display: inline-block; padding: 0.75rem 1.25rem; background: var(--ink); color: var(--paper); border-radius: 4px; text-decoration: none; }
a:hover { background: var(--terracotta); }
</style>
</head>
<body>
<main>
  <h1>A beautiful new idea</h1>
  <p>Describe what you want in plain English. Builder takes it from here.</p>
  <a href="#">Get started</a>
</main>
</body>
</html>
""",
        "README.md": "# Static site built with Helm Builder.\n",
    }


TEMPLATES: dict[str, Callable[[], dict[str, str]]] = {
    "vite_react": _vite_react_landing,
    "static": _static_landing,
}


def get(slug: str) -> dict[str, str]:
    builder = TEMPLATES.get(slug)
    if builder is None:
        return _vite_react_landing()
    return builder()
