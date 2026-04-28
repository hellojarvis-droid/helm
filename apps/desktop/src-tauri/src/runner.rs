//! Computer-use runner — the background worker that turns a queued
//! escalation into a completed one.
//!
//! State machine matching the server contract:
//!     poll → claim(queued) → spawn executor → heartbeat(progress)
//!         → complete(succeeded) | complete(failed)
//!
//! Concurrency: only one task at a time. Computer-use sandboxes assume
//! exclusive control of the screen — running two in parallel would have
//! them step on each other.

use crate::api::{ApiError, Escalation, HelmClient};
use crate::executor::{Executor, ExecutorRequest, Progress};

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{mpsc, Mutex};

const POLL_INTERVAL: Duration = Duration::from_secs(15);
const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(30);

#[derive(Clone)]
pub struct RunnerConfig {
    pub api_base: String,
    pub bearer: String,
    pub device_id: String,
}

pub struct Runner {
    config: Arc<Mutex<Option<RunnerConfig>>>,
    executor: Arc<dyn Executor>,
}

impl Runner {
    pub fn new(executor: Arc<dyn Executor>) -> Self {
        Self {
            config: Arc::new(Mutex::new(None)),
            executor,
        }
    }

    pub async fn set_config(&self, config: RunnerConfig) {
        let mut guard = self.config.lock().await;
        *guard = Some(config);
    }

    pub async fn current_config(&self) -> Option<RunnerConfig> {
        self.config.lock().await.clone()
    }

    /// Long-running loop. Awaits credentials, then polls the queue forever.
    /// Cancellation is cooperative — drop the JoinHandle to stop.
    pub async fn run_forever(self: Arc<Self>) {
        loop {
            let cfg = match self.current_config().await {
                Some(c) => c,
                None => {
                    tokio::time::sleep(POLL_INTERVAL).await;
                    continue;
                }
            };
            let client = HelmClient::new(&cfg.api_base, &cfg.bearer);

            match client.list_queue().await {
                Ok(rows) => {
                    if let Some(target) = pick_next(&rows, &cfg.device_id) {
                        if let Err(e) = self.process_one(&client, &cfg, target).await {
                            log::warn!("runner.process_failed: {e}");
                        }
                    }
                }
                Err(e) => log::warn!("runner.queue_poll_failed: {e}"),
            }

            tokio::time::sleep(POLL_INTERVAL).await;
        }
    }

    async fn process_one(
        &self,
        client: &HelmClient,
        cfg: &RunnerConfig,
        target: Escalation,
    ) -> Result<(), ApiError> {
        // Try to claim if it's still queued. If another desktop won the race,
        // claim() returns 409 and we skip.
        let claimed = if target.status == "queued" {
            match client.claim(&target.id, &cfg.device_id).await {
                Ok(c) => c,
                Err(ApiError::Server { status: 409, .. }) => {
                    log::info!("runner.claim_lost: {}", target.id);
                    return Ok(());
                }
                Err(e) => return Err(e),
            }
        } else {
            // We were already running this one (resume after restart).
            target
        };

        let req = ExecutorRequest {
            escalation_id: claimed.id.clone(),
            task: claimed.task.clone(),
            app_hint: claimed.app_hint.clone(),
        };

        let (progress_tx, mut progress_rx) = mpsc::channel::<Progress>(8);
        let executor_handle = self.executor.run(req, progress_tx);

        let mut heartbeat_interval = tokio::time::interval(HEARTBEAT_INTERVAL);
        // Skip the immediate first tick — we just claimed, the server already
        // recorded a heartbeat in the same row.
        heartbeat_interval.tick().await;

        let final_outcome: Progress = loop {
            tokio::select! {
                msg = progress_rx.recv() => {
                    match msg {
                        Some(Progress::Note(note)) => {
                            if let Err(e) = client
                                .heartbeat(&claimed.id, &cfg.device_id, Some(&note))
                                .await
                            {
                                log::warn!("runner.heartbeat_with_note_failed: {e}");
                            }
                        }
                        Some(p @ Progress::Done(_)) | Some(p @ Progress::Failed(_)) => break p,
                        None => break Progress::Failed(
                            "executor exited without reporting a terminal state".into(),
                        ),
                    }
                }
                _ = heartbeat_interval.tick() => {
                    if let Err(e) = client
                        .heartbeat(&claimed.id, &cfg.device_id, None)
                        .await
                    {
                        log::warn!("runner.heartbeat_failed: {e}");
                    }
                }
            }
        };

        // Wait for the executor task to fully drop so we know nothing is
        // still touching the screen before we report completion.
        let _ = executor_handle.await;

        match final_outcome {
            Progress::Done(result) => {
                client
                    .complete_success(&claimed.id, &cfg.device_id, result)
                    .await?;
            }
            Progress::Failed(err) => {
                client
                    .complete_failure(&claimed.id, &cfg.device_id, &err)
                    .await?;
            }
            Progress::Note(_) => unreachable!("loop only breaks with a terminal outcome"),
        }
        Ok(())
    }
}

fn pick_next(rows: &[Escalation], device_id: &str) -> Option<Escalation> {
    // Prefer resuming a row this device already owns (claimed/running) over
    // claiming a new one — keeps work continuity across desktop restarts.
    if let Some(mine) = rows
        .iter()
        .find(|r| r.claimed_by.as_deref() == Some(device_id) && (r.status == "claimed" || r.status == "running"))
    {
        return Some(mine.clone());
    }
    rows.iter().find(|r| r.status == "queued").cloned()
}
