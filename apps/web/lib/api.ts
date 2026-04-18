import { clientEnv } from "@/lib/env";
import { supabaseBrowser } from "@/lib/supabase/client";

/**
 * Helm API client. Each call attaches the current Supabase access token as
 * a Bearer. For SSE (chat) we use the Fetch API + a manual reader so we can
 * surface ChatEvent objects as they arrive.
 */

export async function authHeader(): Promise<HeadersInit> {
  const supabase = supabaseBrowser();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("not signed in");
  return { Authorization: `Bearer ${token}` };
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const env = clientEnv();
  const headers = {
    ...(init.headers || {}),
    ...(await authHeader()),
  };
  return fetch(`${env.NEXT_PUBLIC_HELM_API_BASE}${path}`, { ...init, headers });
}

// Shape matches helm.agents.runtime.ChatEvent.
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

export async function* streamChat(
  message: string,
  businessId?: string,
  signal?: AbortSignal,
): AsyncIterable<ChatEvent> {
  const env = clientEnv();
  const res = await fetch(`${env.NEXT_PUBLIC_HELM_API_BASE}/chat`, {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(await authHeader()),
    },
    body: JSON.stringify({ message, business_id: businessId ?? null }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status} ${await res.text()}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    // Split on blank-line frame separators (SSE standard).
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice("data: ".length);
        try {
          yield JSON.parse(payload) as ChatEvent;
        } catch {
          // Skip malformed frames — the server shouldn't emit them, but
          // be defensive so one bad frame doesn't kill the whole stream.
        }
      }
    }
  }
}

export interface Business {
  id: string;
  name: string;
  vertical: string;
  status: string;
  weekly_spend_cap_cents: number;
  stripe_onboarding_complete?: boolean;
  created_at: string;
}

export async function listBusinesses(): Promise<Business[]> {
  const res = await apiFetch("/businesses");
  if (!res.ok) throw new Error(`listBusinesses: ${res.status}`);
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
  if (!res.ok) throw new Error(`createBusiness: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function getBusiness(id: string): Promise<
  Business & {
    stripe_account_id: string | null;
    brand_kit: Record<string, unknown>;
  }
> {
  const res = await apiFetch(`/businesses/${id}`);
  if (!res.ok) throw new Error(`getBusiness: ${res.status}`);
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
  if (!res.ok) throw new Error(`startStripeOnboarding: ${res.status} ${await res.text()}`);
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
  if (!res.ok) throw new Error(`getSpend: ${res.status}`);
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
  if (!res.ok) throw new Error(`listEvents: ${res.status}`);
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
  status: "pending" | "approved" | "denied" | "modified" | "expired";
  requested_at: string;
  responded_at: string | null;
  expires_at: string;
  details: Record<string, unknown>;
}

export async function listApprovals(status?: Approval["status"]): Promise<Approval[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await apiFetch(`/approvals${qs}`);
  if (!res.ok) throw new Error(`listApprovals: ${res.status}`);
  return res.json();
}

export async function respondToApproval(
  approvalId: string,
  status: "approved" | "denied",
): Promise<Approval> {
  const res = await apiFetch(`/approvals/${approvalId}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(`respondToApproval: ${res.status} ${await res.text()}`);
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
  if (!res.ok) throw new Error(`getKillSwitch: ${res.status}`);
  return res.json();
}

export async function setKillSwitch(active: boolean): Promise<KillSwitchState> {
  const res = await apiFetch("/users/me/kill_switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  if (!res.ok) throw new Error(`setKillSwitch: ${res.status} ${await res.text()}`);
  return res.json();
}
