# @helm/desktop

Tauri 2 shell that loads the deployed Helm web app. The desktop surface's
distinct capability — computer use — lands on top of this shell.

## Why a shell

The three-surfaces promise (mobile + web + desktop) means the data model
and every user-visible page must serve all three. Rather than duplicate
every component in Rust+WebView, the desktop app loads `apps/web` in a
native window. Shared chat state, shared approvals, shared kill switch
— automatically.

Phase 6 (computer use) adds native capabilities on top: the agent drives
the user's screen for tasks no API covers (TikTok small-budget flows,
supplier portals, etc.). The desktop app streams the sandbox back to
the user for observation. That needs native code; it lands here.

## Local dev

Requires Rust toolchain + the Tauri CLI:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install tauri-cli --version "^2.0"
```

Then from the repo root:

```bash
pnpm web:dev                              # http://localhost:3000
pnpm --filter @helm/desktop tauri:dev     # opens a native window on localhost:3000
```

For a production build (signed + notarized on macOS is a follow-up):

```bash
pnpm --filter @helm/desktop tauri:build
```

Scripts are prefixed `tauri:` so turbo's root pipeline (which runs
`build`, `dev`, `lint`, `test`, `typecheck`) doesn't try to invoke
cargo on CI workers that don't have the Rust toolchain.
