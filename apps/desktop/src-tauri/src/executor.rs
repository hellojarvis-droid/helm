//! Executor trait for computer-use tasks.
//!
//! Phase 6 deliberately keeps the executor pluggable. The wire-up to a real
//! Anthropic computer-use loop (Messages API + screen capture + input
//! injection) is a follow-up — those bits are OS-specific (Wayland vs X11
//! vs macOS Accessibility vs Windows) and warrant their own session.
//!
//! Today we ship `MockExecutor`: it sleeps a configurable amount of time and
//! reports success. That gives us:
//!   1. A working end-to-end queue (CEO escalates → desktop claims → completes)
//!   2. A clean seam to swap in `AnthropicComputerUseExecutor` later without
//!      touching `runner.rs` or the API contract.

use serde_json::{json, Value};
use std::time::Duration;
use tokio::sync::mpsc;

#[derive(Debug, Clone)]
#[allow(dead_code)] // escalation_id is plumbed for future executors that need it for logging / Anthropic session metadata
pub struct ExecutorRequest {
    pub escalation_id: String,
    pub task: String,
    pub app_hint: String,
}

#[derive(Debug, Clone)]
pub enum Progress {
    Note(String),
    Done(Value),
    Failed(String),
}

/// The executor runs the task and emits progress notes plus a final result
/// over `progress_tx`. The runner listens on the receiver and forwards
/// progress to the API as heartbeats / terminal completes.
pub trait Executor: Send + Sync + 'static {
    fn run(
        &self,
        req: ExecutorRequest,
        progress_tx: mpsc::Sender<Progress>,
    ) -> tokio::task::JoinHandle<()>;
}

/// A no-op executor that reports a successful completion after a delay.
/// Useful for end-to-end testing the queue/claim/heartbeat/complete pipeline
/// without wiring up Anthropic + screen control.
pub struct MockExecutor {
    pub work_duration: Duration,
}

impl Default for MockExecutor {
    fn default() -> Self {
        Self {
            work_duration: Duration::from_secs(5),
        }
    }
}

impl Executor for MockExecutor {
    fn run(
        &self,
        req: ExecutorRequest,
        progress_tx: mpsc::Sender<Progress>,
    ) -> tokio::task::JoinHandle<()> {
        let dur = self.work_duration;
        tokio::spawn(async move {
            let _ = progress_tx
                .send(Progress::Note(format!(
                    "Mock executor opening {} for: {}",
                    req.app_hint, req.task
                )))
                .await;
            tokio::time::sleep(dur).await;
            let _ = progress_tx
                .send(Progress::Done(json!({
                    "executor": "mock",
                    "task": req.task,
                    "app_hint": req.app_hint,
                    "note": "Phase 6 placeholder — replace with Anthropic computer-use loop.",
                })))
                .await;
        })
    }
}
