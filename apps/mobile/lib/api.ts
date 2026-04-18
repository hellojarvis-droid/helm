import EventSource from "react-native-sse";
import { mobileEnv } from "./env";
import { supabase } from "./supabase";

/**
 * Helm API client for mobile — mirrors apps/web/lib/api.ts surface, now
 * with true SSE streaming via react-native-sse (XHR-under-the-hood, works
 * in Expo Go + native, new arch safe).
 */

async function authHeader(): Promise<Record<string, string>> {
  const client = supabase();
  const { data } = await client.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("not signed in");
  return { Authorization: `Bearer ${token}` };
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const env = mobileEnv();
  const headers = { ...(init.headers ?? {}), ...(await authHeader()) };
  return fetch(`${env.helmApiBase}${path}`, { ...init, headers });
}

// ──────────────────────────────────────────────────────────
// Chat — SSE streaming (react-native-sse)
// ──────────────────────────────────────────────────────────

// Matches apps/api/helm/agents/runtime.py ChatEvent shape.
export type ChatEvent =
  | { kind: "user_logged"; text: string }
  | { kind: "text_delta"; text: string }
  | { kind: "tool_call"; name: string; input?: Record<string, unknown> }
  | { kind: "tool_result"; name: string; is_error?: boolean }
  | {
      kind: "approval_requested";
      approval_id: string;
      approval_kind: string;
      summary: string;
      details?: Record<string, unknown>;
      business_id: string;
      expires_at: string;
    }
  | { kind: "turn_cost"; input_tokens: number; output_tokens: number; cost_cents: number }
  | { kind: "done" }
  | { kind: "error"; reason: string; detail?: string };

/**
 * Stream a chat turn, yielding ChatEvents as they arrive.
 *
 * `react-native-sse`'s EventSource is callback-based; we bridge to an
 * AsyncIterable via a resolver queue so consumers write `for await (...)`
 * the same way they do on web.
 */
export async function* streamChatTurn(
  message: string,
  businessId?: string,
  signal?: AbortSignal,
): AsyncIterable<ChatEvent> {
  const env = mobileEnv();
  const token = (await supabase().auth.getSession()).data.session?.access_token;
  if (!token) throw new Error("not signed in");

  const es = new EventSource(`${env.helmApiBase}/chat`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message, business_id: businessId ?? null }),
    // Our FastAPI SSE sends one event per data: line; let the library
    // deliver them via "message" events in arrival order.
    pollingInterval: 0,
  });

  // Bridge callbacks → queue. Resolvers line up to pull queued events.
  const queue: ChatEvent[] = [];
  const waiters: Array<(ev: ChatEvent | null) => void> = [];
  let done = false;

  const push = (ev: ChatEvent) => {
    const waiter = waiters.shift();
    if (waiter) waiter(ev);
    else queue.push(ev);
  };
  const finish = () => {
    done = true;
    while (waiters.length) {
      const w = waiters.shift();
      if (w) w(null);
    }
  };

  es.addEventListener("message", (event: { data?: string | null }) => {
    if (typeof event.data !== "string") return;
    try {
      push(JSON.parse(event.data) as ChatEvent);
    } catch {
      // Malformed frame — skip defensively.
    }
  });
  es.addEventListener("error", (event) => {
    const detail =
      typeof (event as { message?: unknown }).message === "string"
        ? (event as { message: string }).message
        : "stream error";
    push({ kind: "error", reason: "sse_error", detail });
    finish();
  });
  es.addEventListener("close", () => finish());

  const onAbort = () => {
    es.close();
    finish();
  };
  signal?.addEventListener("abort", onAbort);

  try {
    while (!done || queue.length > 0) {
      const next = queue.shift();
      if (next) {
        yield next;
        if (next.kind === "done") {
          es.close();
          return;
        }
        continue;
      }
      const incoming = await new Promise<ChatEvent | null>((resolve) => waiters.push(resolve));
      if (incoming === null) return;
      yield incoming;
      if (incoming.kind === "done") {
        es.close();
        return;
      }
    }
  } finally {
    signal?.removeEventListener("abort", onAbort);
    es.close();
  }
}

// ──────────────────────────────────────────────────────────
// Businesses
// ──────────────────────────────────────────────────────────

export interface Business {
  id: string;
  name: string;
  vertical: string;
  status: string;
  weekly_spend_cap_cents: number;
  per_auth_cap_cents: number;
  created_at: string;
}

export async function listBusinesses(): Promise<Business[]> {
  const res = await apiFetch("/businesses");
  if (!res.ok) throw new Error(`listBusinesses ${res.status}`);
  return res.json();
}

export async function createBusiness(body: {
  name: string;
  vertical: string;
  weekly_spend_cap_cents?: number;
}): Promise<Business> {
  const res = await apiFetch("/businesses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createBusiness ${res.status}: ${await res.text()}`);
  return res.json();
}

export type BusinessDetail = Business & {
  stripe_account_id: string | null;
  stripe_card_id: string | null;
  brand_kit: Record<string, unknown>;
  stripe_sync?: {
    attempted: boolean;
    synced?: boolean;
    error?: string;
  } | null;
};

export async function getBusiness(id: string): Promise<BusinessDetail> {
  const res = await apiFetch(`/businesses/${id}`);
  if (!res.ok) throw new Error(`getBusiness ${res.status}`);
  return res.json();
}

export async function updateBusiness(
  id: string,
  body: { weekly_spend_cap_cents?: number; per_auth_cap_cents?: number },
): Promise<BusinessDetail> {
  const res = await apiFetch(`/businesses/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`updateBusiness ${res.status}: ${await res.text()}`);
  return res.json();
}

export interface StripeOnboardResponse {
  account_id: string;
  onboarding_url: string;
  expires_at: number;
  reused_existing_account: boolean;
}

export async function startStripeOnboarding(businessId: string): Promise<StripeOnboardResponse> {
  const res = await apiFetch(`/businesses/${businessId}/stripe/onboard`, { method: "POST" });
  if (!res.ok) throw new Error(`startStripeOnboarding ${res.status}: ${await res.text()}`);
  return res.json();
}

export interface SpendSummary {
  weekly_cap_cents: number;
  week_to_date_cents: number;
  remaining_cents: number;
  llm_cost_cents: number;
  declined_count: number;
  window_days: number;
  since: string;
}

export async function getSpend(businessId: string): Promise<SpendSummary> {
  const res = await apiFetch(`/businesses/${businessId}/spend`);
  if (!res.ok) throw new Error(`getSpend ${res.status}`);
  return res.json();
}

export interface AgentEvent {
  id: number;
  session_id: string;
  business_id: string | null;
  event_type: string;
  agent_name: string;
  payload: Record<string, unknown>;
  cost_cents: number;
  created_at: string;
}

export async function listEvents(
  businessId: string,
  opts: { limit?: number; beforeId?: number } = {},
): Promise<AgentEvent[]> {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.beforeId) params.set("before_id", String(opts.beforeId));
  const qs = params.toString();
  const res = await apiFetch(`/businesses/${businessId}/events${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`listEvents ${res.status}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Integrations (Composio-mediated)
// ──────────────────────────────────────────────────────────

export interface Integration {
  id: string;
  business_id: string;
  toolkit: string;
  composio_connection_id: string;
  status: "pending" | "active" | "failed" | "expired";
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ConnectToolkitResponse {
  integration_id: string;
  toolkit: string;
  redirect_url: string;
  composio_connection_id: string;
  status: string;
}

export async function listIntegrations(businessId: string): Promise<Integration[]> {
  const res = await apiFetch(`/integrations/${businessId}`);
  if (!res.ok) throw new Error(`listIntegrations ${res.status}`);
  return res.json();
}

export async function connectToolkit(
  businessId: string,
  toolkit: string,
): Promise<ConnectToolkitResponse> {
  const res = await apiFetch(`/integrations/${businessId}/connect/${toolkit}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`connectToolkit ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function syncIntegration(integrationId: string): Promise<Integration> {
  const res = await apiFetch(`/integrations/${integrationId}/sync`, { method: "POST" });
  if (!res.ok) throw new Error(`syncIntegration ${res.status}: ${await res.text()}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Kill switch — CLAUDE.md hard rule #2
// ──────────────────────────────────────────────────────────

export interface KillSwitchState {
  active: boolean;
}

export async function getKillSwitch(): Promise<KillSwitchState> {
  const res = await apiFetch("/users/me/kill_switch");
  if (!res.ok) throw new Error(`getKillSwitch ${res.status}`);
  return res.json();
}

export async function setKillSwitch(active: boolean): Promise<KillSwitchState> {
  const res = await apiFetch("/users/me/kill_switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  if (!res.ok) throw new Error(`setKillSwitch ${res.status}: ${await res.text()}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Approvals
// ──────────────────────────────────────────────────────────

export interface Approval {
  id: string;
  business_id: string;
  kind: string;
  summary: string;
  details: Record<string, unknown>;
  status: "pending" | "approved" | "denied" | "modified" | "expired";
  requested_at: string;
  responded_at: string | null;
  expires_at: string;
  // Populated only on /respond responses when raise_weekly_cap changed the cap.
  cap_raise?: {
    changed: boolean;
    old_cap_cents?: number;
    new_cap_cents?: number;
    wtd_cents?: number;
    buffer_cents?: number;
    reason?: string;
  } | null;
}

export async function listApprovals(status?: Approval["status"]): Promise<Approval[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await apiFetch(`/approvals${qs}`);
  if (!res.ok) throw new Error(`listApprovals ${res.status}`);
  return res.json();
}

export async function respondToApproval(
  approvalId: string,
  status: "approved" | "denied" | "modified",
  modifications?: Record<string, unknown>,
): Promise<Approval> {
  const res = await apiFetch(`/approvals/${approvalId}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, modifications: modifications ?? null }),
  });
  if (!res.ok) throw new Error(`respondToApproval ${res.status}: ${await res.text()}`);
  return res.json();
}
