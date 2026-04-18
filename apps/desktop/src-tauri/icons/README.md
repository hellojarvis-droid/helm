# Icons

Tauri bundles require platform icons in this directory:

- `32x32.png`, `128x128.png`, `128x128@2x.png` — Linux PNG
- `icon.icns` — macOS
- `icon.ico` — Windows

Generate them once from a 1024×1024 source PNG:

```bash
cargo tauri icon path/to/helm-source.png
```

Icons aren't needed for `cargo run` (dev), only for `cargo tauri build`.
Not committed to the repo yet — drop in the generated files before the
first release build.
