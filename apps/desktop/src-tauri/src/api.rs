//! Helm API client for the computer-use runner.
//!
//! Thin reqwest wrappers around the `/computer_use/*` endpoints. Auth is a
//! bearer JWT the user picks up by signing in to the embedded web app, then
//! hands to Rust via the `set_credentials` Tauri command. The runner stays
//! idle until it has both a base URL and a token.

use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fmt;
use std::time::Duration;

#[derive(Debug)]
#[allow(dead_code)] // NotConfigured surfaces from future env/config paths
pub enum ApiError {
    Transport(reqwest::Error),
    Server { status: u16, body: String },
    NotConfigured,
}

impl fmt::Display for ApiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ApiError::Transport(e) => write!(f, "transport: {e}"),
            ApiError::Server { status, body } => {
                write!(f, "server returned {status}: {body}")
            }
            ApiError::NotConfigured => write!(f, "not configured"),
        }
    }
}

impl std::error::Error for ApiError {}

impl From<reqwest::Error> for ApiError {
    fn from(e: reqwest::Error) -> Self {
        ApiError::Transport(e)
    }
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)] // user_id/business_id/session_id round-trip from the API; reserved for future routing logic
pub struct Escalation {
    pub id: String,
    pub user_id: String,
    pub business_id: String,
    pub session_id: String,
    pub status: String,
    pub requester: String,
    pub task: String,
    pub app_hint: String,
    pub claimed_by: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ClaimBody<'a> {
    pub claimed_by: &'a str,
}

#[derive(Debug, Clone, Serialize)]
pub struct HeartbeatBody<'a> {
    pub claimed_by: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_note: Option<&'a str>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CompleteBody<'a> {
    pub claimed_by: &'a str,
    pub status: &'a str, // "succeeded" | "failed"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<&'a str>,
}

pub struct HelmClient {
    base: String,
    bearer: String,
    http: Client,
}

impl HelmClient {
    pub fn new(base: impl Into<String>, bearer: impl Into<String>) -> Self {
        let http = Client::builder()
            .timeout(Duration::from_secs(30))
            .user_agent(concat!("helm-desktop/", env!("CARGO_PKG_VERSION")))
            .build()
            .expect("reqwest client");
        Self {
            base: base.into().trim_end_matches('/').to_string(),
            bearer: bearer.into(),
            http,
        }
    }

    fn url(&self, path: &str) -> String {
        format!("{}{}", self.base, path)
    }

    pub async fn list_queue(&self) -> Result<Vec<Escalation>, ApiError> {
        let resp = self
            .http
            .get(self.url("/computer_use/queue"))
            .bearer_auth(&self.bearer)
            .send()
            .await?;
        decode(resp).await
    }

    pub async fn claim(&self, id: &str, claimed_by: &str) -> Result<Escalation, ApiError> {
        let resp = self
            .http
            .post(self.url(&format!("/computer_use/{id}/claim")))
            .bearer_auth(&self.bearer)
            .json(&ClaimBody { claimed_by })
            .send()
            .await?;
        decode(resp).await
    }

    pub async fn heartbeat(
        &self,
        id: &str,
        claimed_by: &str,
        progress_note: Option<&str>,
    ) -> Result<Escalation, ApiError> {
        let resp = self
            .http
            .post(self.url(&format!("/computer_use/{id}/heartbeat")))
            .bearer_auth(&self.bearer)
            .json(&HeartbeatBody {
                claimed_by,
                progress_note,
            })
            .send()
            .await?;
        decode(resp).await
    }

    pub async fn complete_success(
        &self,
        id: &str,
        claimed_by: &str,
        result: Value,
    ) -> Result<Escalation, ApiError> {
        self.complete(id, claimed_by, "succeeded", Some(result), None)
            .await
    }

    pub async fn complete_failure(
        &self,
        id: &str,
        claimed_by: &str,
        error: &str,
    ) -> Result<Escalation, ApiError> {
        self.complete(id, claimed_by, "failed", None, Some(error))
            .await
    }

    async fn complete(
        &self,
        id: &str,
        claimed_by: &str,
        status: &str,
        result: Option<Value>,
        error: Option<&str>,
    ) -> Result<Escalation, ApiError> {
        let body = CompleteBody {
            claimed_by,
            status,
            result,
            error,
        };
        let resp = self
            .http
            .post(self.url(&format!("/computer_use/{id}/complete")))
            .bearer_auth(&self.bearer)
            .json(&body)
            .send()
            .await?;
        decode(resp).await
    }
}

async fn decode<T: serde::de::DeserializeOwned>(resp: reqwest::Response) -> Result<T, ApiError> {
    let status = resp.status();
    if status.is_success() {
        Ok(resp.json::<T>().await?)
    } else {
        let body = resp.text().await.unwrap_or_default();
        Err(ApiError::Server {
            status: status.as_u16(),
            body,
        })
    }
}
