// Prevents a second console window from opening on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod api;
mod executor;
mod runner;

use std::sync::Arc;

use crate::executor::MockExecutor;
use crate::runner::{Runner, RunnerConfig};

/// Helm desktop entry point.
///
/// The window content is the Helm web app — `app.windows[].url` in
/// `tauri.conf.json` points at the deployed host (or localhost:3000 in dev).
/// Phase 6 (computer use) wires a background runner here that polls the
/// API for queued escalations and runs them through the `Executor` trait.
fn main() {
    let runner = Arc::new(Runner::new(Arc::new(MockExecutor::default())));

    tauri::Builder::default()
        .manage(runner.clone())
        .invoke_handler(tauri::generate_handler![
            ping,
            set_credentials,
            runner_status,
        ])
        .setup(move |_app| {
            // Spawn the polling loop on Tauri's tokio runtime. It idles until
            // the web app calls `set_credentials`; that handoff prevents Rust
            // from owning auth before sign-in.
            let runner_for_loop = runner.clone();
            tauri::async_runtime::spawn(async move {
                runner_for_loop.run_forever().await;
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Minimal round-trip so the web app can confirm it's running inside Tauri
/// and light up the computer-use affordance. The runner is the real surface;
/// `ping` exists so the web app can detect the desktop and show "online".
#[tauri::command]
fn ping() -> &'static str {
    "pong"
}

/// Web app hands the runner the API base URL + the user's Supabase JWT once
/// the user has signed in. Without this the runner stays idle. Re-callable
/// to refresh the token before it expires.
#[tauri::command]
async fn set_credentials(
    runner: tauri::State<'_, Arc<Runner>>,
    api_base: String,
    bearer: String,
) -> Result<(), String> {
    let device_id = device_fingerprint();
    runner
        .set_config(RunnerConfig {
            api_base,
            bearer,
            device_id,
        })
        .await;
    Ok(())
}

/// Whether the runner has credentials and is actively polling. The web app
/// shows a small "computer use ready" indicator when this returns true.
#[tauri::command]
async fn runner_status(runner: tauri::State<'_, Arc<Runner>>) -> Result<RunnerStatus, String> {
    let cfg = runner.current_config().await;
    Ok(RunnerStatus {
        configured: cfg.is_some(),
        device_id: cfg.map(|c| c.device_id),
    })
}

#[derive(serde::Serialize)]
struct RunnerStatus {
    configured: bool,
    device_id: Option<String>,
}

/// Per-install identifier the API uses as `claimed_by`. We don't have native
/// machine-uid in the dependency set, so a v4 UUID stamped at first launch
/// is good enough — the API only needs *stable* ids, not globally meaningful
/// ones.
fn device_fingerprint() -> String {
    static ONCE: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    ONCE.get_or_init(|| format!("helm-desktop-{}", uuid::Uuid::new_v4()))
        .clone()
}
