// Prevents a second console window from opening on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

/// Helm desktop entry point.
///
/// The window content is the Helm web app — `app.windows[].url` in
/// `tauri.conf.json` points at the deployed host (or localhost:3000 in
/// dev). Phase 6 (computer use) wires native commands here that drive
/// the user's screen sandbox.
fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![ping])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Minimal round-trip so the web app can confirm it's running inside
/// Tauri and light up the computer-use affordance. Returns the static
/// string "pong" today; Phase 6 grows this into the IPC bridge.
#[tauri::command]
fn ping() -> &'static str {
    "pong"
}
