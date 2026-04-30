import { ApiError, apiErrorFromResponse } from "@/lib/api-error";
import { clientEnv } from "@/lib/env";
import { supabaseBrowser } from "@/lib/supabase/client";

/**
 * Helm API client. Each call attaches the current Supabase access token as
 * a Bearer. For SSE (chat) we use the Fetch API + a manual reader so we can
 * surface ChatEvent objects as they arrive.
 *
 * On !res.ok, every call throws an `ApiError` (see ./api-error) with a
 * user-safe message, the server error code, and the trace ID — callers
 * render `err.userMessage` directly and read `err.code` to branch on
 * specific conditions.
 */

export async function authHeader(): Promise<HeadersInit> {
  const supabase = supabaseBrowser();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) {
    throw new ApiError({
      code: "not_signed_in",
      status: 401,
      userMessage: "You're not signed in. Sign in to continue.",
    });
  }
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

export interface ChatHistoryItem {
  id: number;
  kind: string;
  role: "user" | "agent" | null;
  text: string | null;
  business_id: string | null;
  created_at: string;
  payload: Record<string, unknown>;
  approval: {
    approval_id?: string;
    kind?: string;
    summary?: string;
    status?: string;
    modifications?: Record<string, unknown> | null;
  } | null;
}

export interface ChatHistoryResponse {
  session_id: string;
  items: ChatHistoryItem[];
}

export async function getChatHistory(businessId?: string): Promise<ChatHistoryResponse> {
  const qs = businessId ? `?business_id=${encodeURIComponent(businessId)}` : "";
  const res = await apiFetch(`/chat/history${qs}`);
  if (!res.ok) throw await apiErrorFromResponse(res, "getChatHistory");
  return res.json();
}

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
    // apiErrorFromResponse will try to parse the envelope, so it consumes
    // (via clone) the body — we don't need to drain it ourselves.
    throw await apiErrorFromResponse(res, "streamChat");
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
  per_auth_cap_cents: number;
  allowed_mcc_codes: string[] | null;
  stripe_onboarding_complete?: boolean;
  created_at: string;
}

export async function listBusinesses(): Promise<Business[]> {
  const res = await apiFetch("/businesses");
  if (!res.ok) throw await apiErrorFromResponse(res, "listBusinesses");
  return res.json();
}

export async function createBusiness(body: {
  name: string;
  vertical: string;
  weekly_spend_cap_cents?: number;
  onboarding?: {
    idea?: string;
    enabled_specialists?: string[];
  };
}): Promise<Business> {
  const res = await apiFetch("/businesses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await apiErrorFromResponse(res, "createBusiness");
  return res.json();
}

export type BusinessDetail = Business & {
  stripe_account_id: string | null;
  stripe_card_id?: string | null;
  brand_kit: Record<string, unknown>;
  stripe_sync?: {
    attempted: boolean;
    synced?: boolean;
    error?: string;
  } | null;
};

export async function getBusiness(id: string): Promise<BusinessDetail> {
  const res = await apiFetch(`/businesses/${id}`);
  if (!res.ok) throw await apiErrorFromResponse(res, "getBusiness");
  return res.json();
}

export async function updateBusiness(
  id: string,
  body: {
    weekly_spend_cap_cents?: number;
    per_auth_cap_cents?: number;
    allowed_mcc_codes?: string[] | null;
    reset_mcc_codes_to_default?: boolean;
  },
): Promise<BusinessDetail> {
  const res = await apiFetch(`/businesses/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await apiErrorFromResponse(res, "updateBusiness");
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
  if (!res.ok) throw await apiErrorFromResponse(res, "startStripeOnboarding");
  return res.json();
}

export interface SpendSummary {
  weekly_cap_cents: number;
  week_to_date_cents: number;
  remaining_cents: number;
  llm_cost_cents: number;
  declined_count: number;
  revenue_wtd_cents: number;
  net_wtd_cents: number;
  window_days: number;
  since: string;
}

export async function getSpend(businessId: string): Promise<SpendSummary> {
  const res = await apiFetch(`/businesses/${businessId}/spend`);
  if (!res.ok) throw await apiErrorFromResponse(res, "getSpend");
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
  const queryString = params.toString();
  const res = await apiFetch(
    `/businesses/${businessId}/events${queryString ? `?${queryString}` : ""}`,
  );
  if (!res.ok) throw await apiErrorFromResponse(res, "listEvents");
  return res.json();
}

// Cross-business tenant-scoped events feed. Used by /agents, /events, and
// the Approvals "Why?" trace.
export async function listAllEvents(
  opts: {
    businessId?: string;
    eventType?: string;
    agentName?: string;
    limit?: number;
    beforeId?: number;
  } = {},
): Promise<AgentEvent[]> {
  const params = new URLSearchParams();
  if (opts.businessId) params.set("business_id", opts.businessId);
  if (opts.eventType) params.set("event_type", opts.eventType);
  if (opts.agentName) params.set("agent_name", opts.agentName);
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.beforeId) params.set("before_id", String(opts.beforeId));
  const qs = params.toString();
  const res = await apiFetch(`/events${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`listAllEvents: ${res.status}`);
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

export async function getApproval(id: string): Promise<Approval> {
  const res = await apiFetch(`/approvals/${id}`);
  if (!res.ok) throw await apiErrorFromResponse(res, "getApproval");
  return res.json();
}

export async function listApprovals(status?: Approval["status"]): Promise<Approval[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await apiFetch(`/approvals${qs}`);
  if (!res.ok) throw await apiErrorFromResponse(res, "listApprovals");
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
  if (!res.ok) throw await apiErrorFromResponse(res, "respondToApproval");
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Connectors catalog + account-level connections (bring-your-own-keys)
// ──────────────────────────────────────────────────────────

export interface ConnectorInfo {
  slug: string;
  name: string;
  category: "Creative" | "Commerce" | "Payments" | "Ads" | "Social" | "Ops" | "Communication";
  scope: "account" | "business";
  auth_mode: "composio_oauth" | "api_key";
  description: string;
  signup_url: string | null;
  connect_hint: string;
  popularity: number;
  cost_hint: string;
  icon_slug: string | null;
}

export async function getConnectorCatalog(): Promise<ConnectorInfo[]> {
  const res = await apiFetch(`/connectors/catalog`);
  if (!res.ok) throw new Error(`getConnectorCatalog: ${res.status}`);
  return res.json();
}

export interface ConnectionStatus {
  id: string;
  toolkit: string;
  auth_mode: "composio_oauth" | "api_key";
  status: "pending" | "active" | "failed" | "expired";
  has_api_key: boolean;
  masked_key: string | null;
  composio_connection_id: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export async function listAccountConnections(): Promise<ConnectionStatus[]> {
  const res = await apiFetch(`/connections/account`);
  if (!res.ok) throw new Error(`listAccountConnections: ${res.status}`);
  return res.json();
}

export async function saveAccountApiKey(slug: string, apiKey: string): Promise<ConnectionStatus> {
  const res = await apiFetch(`/connections/account/api_key/${slug}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) throw new Error(`saveAccountApiKey: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function startAccountOAuth(
  slug: string,
): Promise<{ connection_id: string; toolkit: string; redirect_url: string; status: string }> {
  const res = await apiFetch(`/connections/account/oauth/${slug}`, { method: "POST" });
  if (!res.ok) throw new Error(`startAccountOAuth: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function disconnectAccount(slug: string): Promise<void> {
  const res = await apiFetch(`/connections/account/${slug}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`disconnectAccount: ${res.status} ${await res.text()}`);
  }
}

export async function syncAccountConnection(slug: string): Promise<ConnectionStatus> {
  const res = await apiFetch(`/connections/account/${slug}/sync`, { method: "POST" });
  if (!res.ok) throw new Error(`syncAccountConnection: ${res.status} ${await res.text()}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Creative Studio renders
// ──────────────────────────────────────────────────────────

export type RenderStatus = "pending" | "queued" | "running" | "completed" | "failed" | "cancelled";

export interface RenderJob {
  id: string;
  user_id: string;
  business_id: string | null;
  provider: string;
  mode: "image" | "video";
  prompt: string;
  options: Record<string, unknown>;
  status: RenderStatus;
  external_job_id: string | null;
  output_url: string | null;
  thumbnail_url: string | null;
  cost_cents_estimate: number;
  cost_cents_actual: number | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface StartRenderRequest {
  provider: string;
  mode: "image" | "video";
  prompt: string;
  business_id?: string;
  options?: Record<string, unknown>;
}

export async function startRender(body: StartRenderRequest): Promise<RenderJob> {
  const res = await apiFetch("/renders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`startRender: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function listRenders(
  opts: { businessId?: string; limit?: number } = {},
): Promise<RenderJob[]> {
  const params = new URLSearchParams();
  if (opts.businessId) params.set("business_id", opts.businessId);
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  const res = await apiFetch(`/renders${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`listRenders: ${res.status}`);
  return res.json();
}

export async function cancelRender(id: string): Promise<RenderJob> {
  const res = await apiFetch(`/renders/${id}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(`cancelRender: ${res.status} ${await res.text()}`);
  return res.json();
}

export interface RenderCostEstimate {
  provider: string;
  mode: "image" | "video";
  cost_cents_estimate: number;
  supported: boolean;
  note: string;
}

export async function estimateRenderCost(body: {
  provider: string;
  mode: "image" | "video";
  options?: Record<string, unknown>;
}): Promise<RenderCostEstimate> {
  const res = await apiFetch("/renders/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, options: body.options ?? {} }),
  });
  if (!res.ok) throw new Error(`estimateRenderCost: ${res.status}`);
  return res.json();
}

export type RenderStreamEvent =
  | { kind: "snapshot"; renders: RenderJob[] }
  | { kind: "renders"; renders: RenderJob[] }
  | { kind: "timeout" };

export async function* streamRenders(
  opts: { businessId?: string; signal?: AbortSignal } = {},
): AsyncIterable<RenderStreamEvent> {
  const env = clientEnv();
  const qs = opts.businessId ? `?business_id=${opts.businessId}` : "";
  const res = await fetch(`${env.NEXT_PUBLIC_HELM_API_BASE}/renders/stream${qs}`, {
    signal: opts.signal,
    headers: {
      Accept: "text/event-stream",
      ...(await authHeader()),
    },
  });
  if (!res.ok || !res.body) {
    throw new Error(`streamRenders: ${res.status} ${await res.text()}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      let name = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7).trim();
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!data) continue;
      try {
        const parsed = JSON.parse(data) as { renders?: RenderJob[] };
        if (name === "snapshot") {
          yield { kind: "snapshot", renders: parsed.renders ?? [] };
        } else if (name === "renders") {
          yield { kind: "renders", renders: parsed.renders ?? [] };
        } else if (name === "timeout") {
          yield { kind: "timeout" };
          return;
        }
      } catch {
        // ignore malformed frame
      }
    }
  }
}

export interface ApprovalTrace {
  approval_id: string;
  session_id: string | null;
  events: {
    id: number;
    event_type: string;
    agent_name: string;
    payload: Record<string, unknown>;
    cost_cents: number;
    created_at: string;
  }[];
  total_cost_cents: number;
}

export async function getApprovalTrace(approvalId: string): Promise<ApprovalTrace> {
  const res = await apiFetch(`/approvals/${approvalId}/trace`);
  if (!res.ok) throw new Error(`getApprovalTrace: ${res.status}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Today — cross-business aggregate
// ──────────────────────────────────────────────────────────

export interface BusinessToday {
  id: string;
  name: string;
  vertical: string;
  status: string;
  revenue_today_cents: number;
  spend_today_cents: number;
  net_today_cents: number;
  pending_approval_count: number;
}

export interface TodaySummary {
  revenue_today_cents: number;
  spend_today_cents: number;
  net_today_cents: number;
  pending_approval_count: number;
  window_hours: number;
  since: string;
  businesses: BusinessToday[];
}

export async function getToday(): Promise<TodaySummary> {
  const res = await apiFetch("/users/me/today");
  if (!res.ok) throw await apiErrorFromResponse(res, "getToday");
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
  if (!res.ok) throw await apiErrorFromResponse(res, "getKillSwitch");
  return res.json();
}

export async function setKillSwitch(active: boolean): Promise<KillSwitchState> {
  const res = await apiFetch("/users/me/kill_switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  if (!res.ok) throw await apiErrorFromResponse(res, "setKillSwitch");
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Billing — tier limits + usage
// ──────────────────────────────────────────────────────────

export interface BillingState {
  tier: string;
  display_name: string;
  max_businesses: number; // 0 = unlimited
  monthly_tokens: number; // 0 = unlimited
  businesses_used: number;
  month_to_date_cost_cents: number;
  subscription_status: string;
}

export async function getBilling(): Promise<BillingState> {
  const res = await apiFetch("/billing/me");
  if (!res.ok) throw await apiErrorFromResponse(res, "getBilling");
  return res.json();
}

export async function startBillingCheckout(
  targetTier: "founder" | "operator" | "portfolio",
): Promise<{ url: string }> {
  const res = await apiFetch("/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_tier: targetTier }),
  });
  if (!res.ok) throw await apiErrorFromResponse(res, "startBillingCheckout");
  return res.json();
}

export async function openBillingPortal(): Promise<{ url: string }> {
  const res = await apiFetch("/billing/portal", { method: "POST" });
  if (!res.ok) throw await apiErrorFromResponse(res, "openBillingPortal");
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Credits — balance, history, top-up flow
// ──────────────────────────────────────────────────────────

export type PaymentMethod = "card" | "us_bank_account";

export interface CreditBalanceState {
  balance_cents: number;
  lifetime_granted_cents: number;
  lifetime_purchased_cents: number;
  lifetime_spent_cents: number;
  starter_granted: boolean;
  min_top_up_cents: number;
}

export async function getCreditBalance(): Promise<CreditBalanceState> {
  const res = await apiFetch(`/credits/balance`);
  if (!res.ok) throw new Error(`getCreditBalance: ${res.status}`);
  return res.json();
}

export interface CreditTransaction {
  id: string;
  kind:
    | "starter_grant"
    | "subscription_grant"
    | "purchase"
    | "reserve"
    | "commit"
    | "refund"
    | "adjustment";
  amount_cents: number;
  balance_after_cents: number;
  reservation_id: string | null;
  reference_type: string | null;
  reference_id: string | null;
  description: string;
  created_at: string;
  meta: Record<string, unknown>;
}

export async function listCreditTransactions(
  opts: {
    kind?: CreditTransaction["kind"];
    limit?: number;
    beforeId?: string;
  } = {},
): Promise<CreditTransaction[]> {
  const params = new URLSearchParams();
  if (opts.kind) params.set("kind", opts.kind);
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.beforeId) params.set("before_id", opts.beforeId);
  const qs = params.toString();
  const res = await apiFetch(`/credits/transactions${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`listCreditTransactions: ${res.status}`);
  return res.json();
}

export interface TopUpQuote {
  credit_amount_cents: number;
  fee_cents: number;
  total_charge_cents: number;
  payment_method: PaymentMethod;
  fee_explanation: string;
}

export async function quoteTopUp(body: {
  credit_amount_cents: number;
  payment_method: PaymentMethod;
}): Promise<TopUpQuote> {
  const res = await apiFetch(`/credits/top_up/quote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`quoteTopUp: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function startTopUp(body: {
  credit_amount_cents: number;
  payment_method: PaymentMethod;
}): Promise<{
  url: string;
  credit_amount_cents: number;
  fee_cents: number;
  total_charge_cents: number;
}> {
  const res = await apiFetch(`/credits/top_up`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`startTopUp: ${res.status} ${await res.text()}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Per-business integrations
// ──────────────────────────────────────────────────────────

export interface BusinessIntegration {
  id: string;
  business_id: string;
  toolkit: string;
  auth_mode: "composio_oauth" | "api_key";
  composio_connection_id: string | null;
  has_api_key: boolean;
  masked_key: string | null;
  status: "pending" | "active" | "failed" | "expired";
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function listBusinessIntegrations(businessId: string): Promise<BusinessIntegration[]> {
  const res = await apiFetch(`/integrations/${businessId}`);
  if (!res.ok) throw new Error(`listBusinessIntegrations: ${res.status}`);
  return res.json();
}

export async function startBusinessOAuth(
  businessId: string,
  slug: string,
): Promise<{ integration_id: string; toolkit: string; redirect_url: string; status: string }> {
  const res = await apiFetch(`/integrations/${businessId}/connect/${slug}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`startBusinessOAuth: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function saveBusinessApiKey(
  businessId: string,
  slug: string,
  apiKey: string,
): Promise<BusinessIntegration> {
  const res = await apiFetch(`/integrations/${businessId}/api_key/${slug}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) throw new Error(`saveBusinessApiKey: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function disconnectBusinessIntegration(
  businessId: string,
  slug: string,
): Promise<void> {
  const res = await apiFetch(`/integrations/${businessId}/${slug}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`disconnectBusinessIntegration: ${res.status} ${await res.text()}`);
  }
}

export async function syncBusinessIntegration(integrationId: string): Promise<BusinessIntegration> {
  const res = await apiFetch(`/integrations/${integrationId}/sync`, { method: "POST" });
  if (!res.ok) throw new Error(`syncBusinessIntegration: ${res.status}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Helm Storefront + products
// ──────────────────────────────────────────────────────────

export interface HelmStorefront {
  id: string;
  business_id: string;
  slug: string;
  title: string;
  tagline: string | null;
  theme: Record<string, unknown>;
  published: boolean;
  created_at: string;
  updated_at: string;
}

export interface HelmProduct {
  id: string;
  business_id: string;
  sku: string | null;
  name: string;
  description: string | null;
  price_cents: number;
  compare_at_price_cents: number | null;
  currency: string;
  inventory_qty: number | null;
  images: string[];
  external_refs: Record<string, unknown>;
  published: boolean;
  created_at: string;
  updated_at: string;
}

export interface UpsertStorefrontBody {
  slug: string;
  title: string;
  tagline?: string | null;
  theme?: Record<string, unknown>;
  published?: boolean;
}

export interface UpsertProductBody {
  sku?: string | null;
  name: string;
  description?: string | null;
  price_cents: number;
  compare_at_price_cents?: number | null;
  currency?: string;
  inventory_qty?: number | null;
  images?: string[];
  published?: boolean;
}

export async function upsertStorefront(
  businessId: string,
  body: UpsertStorefrontBody,
): Promise<HelmStorefront> {
  const res = await apiFetch(`/businesses/${businessId}/storefront`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`upsertStorefront: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function getStorefront(businessId: string): Promise<HelmStorefront | null> {
  const res = await apiFetch(`/businesses/${businessId}/storefront`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`getStorefront: ${res.status}`);
  return res.json();
}

export async function listProducts(businessId: string): Promise<HelmProduct[]> {
  const res = await apiFetch(`/businesses/${businessId}/products`);
  if (!res.ok) throw new Error(`listProducts: ${res.status}`);
  return res.json();
}

export async function createProduct(
  businessId: string,
  body: UpsertProductBody,
): Promise<HelmProduct> {
  const res = await apiFetch(`/businesses/${businessId}/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createProduct: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function updateProduct(
  businessId: string,
  productId: string,
  body: Partial<UpsertProductBody>,
): Promise<HelmProduct> {
  const res = await apiFetch(`/businesses/${businessId}/products/${productId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`updateProduct: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function deleteProduct(businessId: string, productId: string): Promise<void> {
  const res = await apiFetch(`/businesses/${businessId}/products/${productId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`deleteProduct: ${res.status} ${await res.text()}`);
  }
}

export interface PublicStorefront {
  slug: string;
  title: string;
  tagline: string | null;
  theme: Record<string, unknown>;
  business_name: string;
  products: HelmProduct[];
}

// Public fetch (no auth). Uses raw fetch so we don't attach the Supabase
// bearer for a customer-facing page load.
export async function getPublicStorefront(slug: string): Promise<PublicStorefront> {
  const env = clientEnv();
  const res = await fetch(`${env.NEXT_PUBLIC_HELM_API_BASE}/s/${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`getPublicStorefront: ${res.status}`);
  return res.json();
}

export async function startPublicCheckout(
  slug: string,
  productId: string,
  quantity: number = 1,
): Promise<{ url: string }> {
  const env = clientEnv();
  const res = await fetch(
    `${env.NEXT_PUBLIC_HELM_API_BASE}/s/${encodeURIComponent(slug)}/checkout`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId, quantity }),
    },
  );
  if (!res.ok) throw new Error(`startPublicCheckout: ${res.status} ${await res.text()}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Sync status — bidirectional-sync bookkeeping per business
// ──────────────────────────────────────────────────────────

export interface SyncStatus {
  entity_type: string;
  external_id: string;
  last_direction: "push" | "pull";
  last_status: "ok" | "failed" | "conflict";
  last_error: string | null;
  local_updated_at: string;
  external_updated_at: string | null;
}

export async function getBusinessSyncStatus(businessId: string): Promise<SyncStatus[]> {
  const res = await apiFetch(`/businesses/${businessId}/sync_status`);
  if (!res.ok) throw new Error(`getBusinessSyncStatus: ${res.status}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────
// Launches — Phase 3 staged business-launch workflow
// ──────────────────────────────────────────────────────────

export interface LaunchStep {
  id: string;
  step_name: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  step_order: number;
  started_at: string | null;
  completed_at: string | null;
  output: Record<string, unknown>;
  error: string | null;
}

export interface LaunchSnapshot {
  launch_id: string;
  business_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  current_step: string | null;
  started_at: string;
  completed_at: string | null;
  error: string | null;
  steps: LaunchStep[];
}

export async function startLaunch(businessId: string): Promise<LaunchSnapshot> {
  const res = await apiFetch(`/businesses/${businessId}/launch`, { method: "POST" });
  if (!res.ok) throw new Error(`startLaunch: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function getLaunch(businessId: string): Promise<LaunchSnapshot | null> {
  const res = await apiFetch(`/businesses/${businessId}/launch`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`getLaunch: ${res.status}`);
  return res.json();
}

export type LaunchStreamEvent =
  | { kind: "snapshot"; snapshot: LaunchSnapshot }
  | { kind: "step"; event_type: string; agent_name: string; payload: Record<string, unknown> }
  | { kind: "done" }
  | { kind: "timeout" };

// SSE reader for /businesses/{id}/launch/stream. Yields typed events so the
// launch theater can route on kind + event_type. The stream naturally
// terminates when the launch hits a terminal state.
export async function* streamLaunch(
  businessId: string,
  signal?: AbortSignal,
): AsyncIterable<LaunchStreamEvent> {
  const env = clientEnv();
  const res = await fetch(
    `${env.NEXT_PUBLIC_HELM_API_BASE}/businesses/${businessId}/launch/stream`,
    {
      signal,
      headers: {
        Accept: "text/event-stream",
        ...(await authHeader()),
      },
    },
  );
  if (!res.ok || !res.body) {
    throw new Error(`streamLaunch: ${res.status} ${await res.text()}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      let eventName = "message";
      let dataLine = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) eventName = line.slice("event: ".length).trim();
        else if (line.startsWith("data: ")) dataLine = line.slice("data: ".length);
      }
      if (!dataLine) continue;
      try {
        const parsed = JSON.parse(dataLine) as Record<string, unknown>;
        if (eventName === "snapshot" || parsed.kind === "snapshot") {
          yield { kind: "snapshot", snapshot: parsed as unknown as LaunchSnapshot };
        } else if (eventName === "done") {
          yield { kind: "done" };
          return;
        } else if (eventName === "timeout") {
          yield { kind: "timeout" };
          return;
        } else {
          yield {
            kind: "step",
            event_type: eventName,
            agent_name: (parsed.agent_name as string) ?? "",
            payload: (parsed.payload as Record<string, unknown>) ?? {},
          };
        }
      } catch {
        // ignore malformed frame
      }
    }
  }
}

// ── Brand Library ────────────────────────────────────────────────────

export interface BrandLibrary {
  id: string;
  business_id: string;
  name: string;
  tagline: string | null;
  source_url: string | null;
  palette: Record<string, unknown>;
  typography: Record<string, unknown>;
  logos: Record<string, unknown>[];
  voice_paragraph: string | null;
  banned_phrases: string[];
  winning_references: Record<string, unknown>[];
  moodboard_urls: string[];
  created_at: string;
  updated_at: string;
}

export interface BrandScrapeResult {
  source_url: string;
  extracted: {
    name?: string;
    tagline?: string | null;
    palette?: {
      primary?: string;
      secondary?: string;
      accent?: string;
      neutral?: string;
    };
    typography?: { display?: string | null; body?: string | null };
    voice_paragraph?: string;
    tone_descriptors?: string[];
    moodboard_keywords?: string[];
    category_signals?: string[];
  } & Record<string, unknown>;
}

export async function getBrandLibrary(businessId: string): Promise<BrandLibrary | null> {
  const res = await apiFetch(`/businesses/${businessId}/brand_library`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`getBrandLibrary: ${res.status}`);
  return (await res.json()) as BrandLibrary;
}

export async function upsertBrandLibrary(
  businessId: string,
  body: Partial<Omit<BrandLibrary, "id" | "business_id" | "created_at" | "updated_at">> & {
    name: string;
  },
): Promise<BrandLibrary> {
  const res = await apiFetch(`/businesses/${businessId}/brand_library`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`upsertBrandLibrary: ${res.status}`);
  return (await res.json()) as BrandLibrary;
}

export class InsufficientCreditsError extends Error {
  needed_cents: number;
  balance_cents: number;
  constructor(needed: number, balance: number) {
    super("insufficient_credits");
    this.needed_cents = needed;
    this.balance_cents = balance;
  }
}

// ── Creative Studio: campaigns + creatives ──────────────────────────

export interface Campaign {
  id: string;
  business_id: string;
  name: string;
  goal: string | null;
  status: "drafting" | "rendering" | "ready" | "archived";
  created_at: string;
  updated_at: string;
}

export interface MasterCreative {
  id: string;
  campaign_id: string;
  brief_id: string | null;
  title: string;
  canonical_aspect: string;
  status: "drafting" | "rendering" | "ready" | "failed" | "archived";
  copy: {
    copy?: {
      headline?: string;
      subhead?: string;
      vo_script?: { shot: number; line: string }[];
      on_screen_text?: { shot: number; text: string }[];
      caption_meta?: string;
      caption_tiktok?: string;
      cta?: string;
    };
    art?: Record<string, unknown>;
    video?: Record<string, unknown>;
    voice?: {
      voice_id?: string;
      voice_name?: string;
      rationale?: string;
      pacing?: { shot: number; wpm: number; energy: string }[];
    };
  };
  timeline_json: Record<string, unknown> | null;
  canonical_output_url: string | null;
  thumbnail_url: string | null;
  imported: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface CreativeShot {
  id: string;
  master_creative_id: string;
  shot_order: number;
  provider: string;
  prompt: string;
  duration_seconds: number;
  options: Record<string, unknown>;
  status: "pending" | "queued" | "running" | "completed" | "failed" | "cancelled";
  output_url: string | null;
  thumbnail_url: string | null;
  cost_cents: number | null;
  error: string | null;
}

export async function listCampaigns(businessId: string): Promise<Campaign[]> {
  const res = await apiFetch(`/businesses/${businessId}/campaigns`);
  if (!res.ok) throw new Error(`listCampaigns: ${res.status}`);
  return (await res.json()) as Campaign[];
}

export async function createCampaign(
  businessId: string,
  body: { name: string; goal?: string | null },
): Promise<Campaign> {
  const res = await apiFetch(`/businesses/${businessId}/campaigns`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createCampaign: ${res.status}`);
  return (await res.json()) as Campaign;
}

export async function generateCreative(
  campaignId: string,
  body: { title: string; user_intent: string; aspect_ratio?: string },
): Promise<MasterCreative> {
  const res = await apiFetch(`/campaigns/${campaignId}/creatives`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 402) {
    const data = (await res.json()) as {
      detail?: { needed_cents: number; balance_cents: number };
    };
    const d = data.detail;
    throw new InsufficientCreditsError(d?.needed_cents ?? 0, d?.balance_cents ?? 0);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`generateCreative: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as MasterCreative;
}

export async function listCreatives(campaignId: string): Promise<MasterCreative[]> {
  const res = await apiFetch(`/campaigns/${campaignId}/creatives`);
  if (!res.ok) throw new Error(`listCreatives: ${res.status}`);
  return (await res.json()) as MasterCreative[];
}

export async function importExistingCreative(
  businessId: string,
  body: {
    campaign_id: string;
    title: string;
    video_url: string;
    description?: string;
    aspect_ratio?: string;
    transcribe?: boolean;
  },
): Promise<MasterCreative> {
  const res = await apiFetch(`/businesses/${businessId}/creatives/import`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 402) {
    const data = (await res.json()) as {
      detail?: { needed_cents: number; balance_cents: number };
    };
    const d = data.detail;
    throw new InsufficientCreditsError(d?.needed_cents ?? 0, d?.balance_cents ?? 0);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`importExistingCreative: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as MasterCreative;
}

export async function listLibrary(
  businessId: string,
  opts: { q?: string; status?: string; aspect?: string; limit?: number } = {},
): Promise<MasterCreative[]> {
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.status) params.set("status", opts.status);
  if (opts.aspect) params.set("aspect", opts.aspect);
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  const path = `/businesses/${businessId}/creatives${qs ? `?${qs}` : ""}`;
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`listLibrary: ${res.status}`);
  return (await res.json()) as MasterCreative[];
}

export async function getCreative(creativeId: string): Promise<MasterCreative> {
  const res = await apiFetch(`/creatives/${creativeId}`);
  if (!res.ok) throw new Error(`getCreative: ${res.status}`);
  return (await res.json()) as MasterCreative;
}

export async function listCreativeShots(creativeId: string): Promise<CreativeShot[]> {
  const res = await apiFetch(`/creatives/${creativeId}/shots`);
  if (!res.ok) throw new Error(`listCreativeShots: ${res.status}`);
  return (await res.json()) as CreativeShot[];
}

export interface PatchCreativeBody {
  title?: string;
  headline?: string;
  subhead?: string;
  cta?: string;
  caption_meta?: string;
  caption_tiktok?: string;
  tags?: string[];
}

export async function patchCreative(
  creativeId: string,
  body: PatchCreativeBody,
): Promise<MasterCreative> {
  const res = await apiFetch(`/creatives/${creativeId}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patchCreative: ${res.status}`);
  return (await res.json()) as MasterCreative;
}

export interface FormatRender {
  id: string;
  master_creative_id: string;
  platform: string;
  aspect: string;
  mode: "video" | "image" | "carousel";
  status: "pending" | "rendering" | "ready" | "failed" | "skipped";
  output_url: string | null;
  thumbnail_url: string | null;
  platform_copy: Record<string, unknown>;
  cost_cents: number | null;
  error: string | null;
  created_at: string;
}

export interface ReformatTarget {
  platform: string;
  aspect: "9:16" | "1:1" | "16:9" | "4:5";
  mode?: "video" | "image" | "carousel";
}

export async function listFormats(creativeId: string): Promise<FormatRender[]> {
  const res = await apiFetch(`/creatives/${creativeId}/formats`);
  if (!res.ok) throw new Error(`listFormats: ${res.status}`);
  return (await res.json()) as FormatRender[];
}

export async function reformatCreative(
  creativeId: string,
  targets: ReformatTarget[],
): Promise<FormatRender[]> {
  const res = await apiFetch(`/creatives/${creativeId}/reformat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ targets }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`reformatCreative: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as FormatRender[];
}

export async function listFormatPrefs(businessId: string): Promise<ReformatTarget[][]> {
  const res = await apiFetch(`/businesses/${businessId}/format_prefs`);
  if (!res.ok) throw new Error(`listFormatPrefs: ${res.status}`);
  return (await res.json()) as ReformatTarget[][];
}

// ── Scheduled posts ──────────────────────────────────────────────────

export interface ScheduledPost {
  id: string;
  master_creative_id: string;
  business_id: string;
  platform: string;
  aspect: string;
  scheduled_at: string;
  status: "scheduled" | "publishing" | "published" | "failed" | "cancelled";
  caption: string;
  video_url: string | null;
  thumbnail_url: string | null;
  meta: Record<string, unknown>;
  external_post_id: string | null;
  external_post_url: string | null;
  error: string | null;
  published_at: string | null;
  cancelled_at: string | null;
  created_at: string;
}

export interface ScheduleTarget {
  platform: string;
  aspect: "9:16" | "1:1" | "16:9" | "4:5";
  caption?: string;
}

export async function scheduleCreative(
  creativeId: string,
  body: {
    scheduled_at: string;
    targets: ScheduleTarget[];
    require_approval?: boolean;
  },
): Promise<ScheduledPost[]> {
  const res = await apiFetch(`/creatives/${creativeId}/schedule`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`scheduleCreative: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as ScheduledPost[];
}

export async function listCreativeSchedule(creativeId: string): Promise<ScheduledPost[]> {
  const res = await apiFetch(`/creatives/${creativeId}/schedule`);
  if (!res.ok) throw new Error(`listCreativeSchedule: ${res.status}`);
  return (await res.json()) as ScheduledPost[];
}

export async function listBusinessSchedule(businessId: string): Promise<ScheduledPost[]> {
  const res = await apiFetch(`/businesses/${businessId}/schedule`);
  if (!res.ok) throw new Error(`listBusinessSchedule: ${res.status}`);
  return (await res.json()) as ScheduledPost[];
}

// ── Expenses + tax export ────────────────────────────────────────────

export type ExpenseCategory =
  | "advertising"
  | "cogs"
  | "software"
  | "contractors"
  | "travel"
  | "meals"
  | "utilities"
  | "supplies"
  | "legal"
  | "bank_fees"
  | "shipping"
  | "other";

export interface Expense {
  id: string;
  business_id: string;
  occurred_at: string;
  amount_cents: number;
  currency: string;
  vendor: string;
  category: ExpenseCategory;
  source: "email" | "manual" | "card";
  source_ref: string | null;
  description: string | null;
  receipt_url: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}

export async function listExpenses(
  businessId: string,
  opts: { year?: number; category?: ExpenseCategory } = {},
): Promise<Expense[]> {
  const params = new URLSearchParams();
  if (opts.year) params.set("year", String(opts.year));
  if (opts.category) params.set("category", opts.category);
  const qs = params.toString();
  const res = await apiFetch(`/businesses/${businessId}/expenses${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`listExpenses: ${res.status}`);
  return (await res.json()) as Expense[];
}

export async function createExpense(
  businessId: string,
  body: {
    occurred_at: string;
    amount_cents: number;
    currency?: string;
    vendor: string;
    category: ExpenseCategory;
    description?: string;
    receipt_url?: string;
  },
): Promise<Expense> {
  const res = await apiFetch(`/businesses/${businessId}/expenses`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createExpense: ${res.status}`);
  return (await res.json()) as Expense;
}

export async function deleteExpense(expenseId: string): Promise<void> {
  const res = await apiFetch(`/expenses/${expenseId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deleteExpense: ${res.status}`);
}

export function expensesExportUrl(businessId: string, year?: number): string {
  const base = `/businesses/${businessId}/expenses/export.csv`;
  return year ? `${base}?year=${year}` : base;
}

export async function downloadExpensesCsv(businessId: string, year?: number): Promise<Blob> {
  const path = expensesExportUrl(businessId, year);
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`downloadExpensesCsv: ${res.status}`);
  return await res.blob();
}

export async function cancelScheduledPost(postId: string): Promise<ScheduledPost> {
  const res = await apiFetch(`/scheduled_posts/${postId}/cancel`, {
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`cancelScheduledPost: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as ScheduledPost;
}

export async function regenerateShot(
  shotId: string,
  body: { prompt?: string; provider?: string },
): Promise<CreativeShot> {
  const res = await apiFetch(`/shots/${shotId}/regenerate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`regenerateShot: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as CreativeShot;
}

export async function scrapeBrandFromUrl(
  businessId: string,
  url: string,
): Promise<BrandScrapeResult> {
  const res = await apiFetch(`/businesses/${businessId}/brand_library/scrape`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (res.status === 402) {
    const body = (await res.json()) as {
      detail?: { needed_cents: number; balance_cents: number };
    };
    const d = body.detail;
    throw new InsufficientCreditsError(d?.needed_cents ?? 0, d?.balance_cents ?? 0);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`scrapeBrandFromUrl: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as BrandScrapeResult;
}

// ── Canvas Creative Studio ──────────────────────────────────────────

export type CanvasTool = "image" | "video" | "edit" | "enhance" | "lipsync";
export type ReferenceRole =
  | "character"
  | "style"
  | "describe"
  | "magic_fill"
  | "background_replace";

export interface ModelEntry {
  slug: string;
  name: string;
  provider: string;
  modalities: string[];
  cost_credits: number;
  avg_seconds: number;
  best_for: string;
  description: string;
  recommended_for: string[];
  helm_managed: boolean;
  deprecated: boolean;
}

export interface ReferenceChipT {
  url: string;
  role: ReferenceRole;
  label?: string | null;
}

export interface Generation {
  id: string;
  user_id: string;
  business_id: string | null;
  session_id: string;
  parent_generation_id: string | null;
  tool: CanvasTool;
  model: string;
  prompt: string;
  params: Record<string, unknown>;
  references: Array<Record<string, unknown>>;
  status: "pending" | "queued" | "running" | "completed" | "failed" | "cancelled";
  output_url: string | null;
  thumbnail_url: string | null;
  cost_cents_reserved: number | null;
  cost_cents_actual: number | null;
  error: string | null;
  favorited: boolean;
  created_at: string;
  updated_at: string;
}

export interface CharacterT {
  id: string;
  business_id: string;
  name: string;
  reference_image_urls: string[];
  trained_provider: string | null;
  trained_ref_id: string | null;
  status: "untrained" | "training" | "ready" | "failed";
  meta: Record<string, unknown>;
  created_at: string;
}

export interface StyleT {
  id: string;
  business_id: string;
  name: string;
  reference_image_urls: string[];
  palette: Record<string, unknown>;
  notes: string | null;
  created_at: string;
}

export interface PresetT {
  id: string;
  user_id: string;
  name: string;
  tool: CanvasTool;
  model: string;
  params: Record<string, unknown>;
  prompt_template: string | null;
  created_at: string;
}

export interface UsageAggregate {
  tool: CanvasTool;
  model: string;
  count: number;
  total_cost_cents: number;
  avg_seconds: number | null;
  last_used: string | null;
}

export interface UsageResponse {
  totals: { count: number; cost_cents: number };
  per_model: UsageAggregate[];
}

export async function listModels(tool?: CanvasTool): Promise<ModelEntry[]> {
  const path = tool ? `/models?tool=${tool}` : "/models";
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`listModels: ${res.status}`);
  return (await res.json()) as ModelEntry[];
}

export async function listViralPresets(): Promise<
  Array<{ slug: string; label: string; tool: CanvasTool; prompt_suffix: string }>
> {
  const res = await apiFetch(`/models/viral_presets`);
  if (!res.ok) throw new Error(`listViralPresets: ${res.status}`);
  return (await res.json()) as Array<{
    slug: string;
    label: string;
    tool: CanvasTool;
    prompt_suffix: string;
  }>;
}

export async function listCameraPresets(): Promise<
  Array<{ slug: string; label: string; prompt_suffix: string }>
> {
  const res = await apiFetch(`/models/camera_presets`);
  if (!res.ok) throw new Error(`listCameraPresets: ${res.status}`);
  return (await res.json()) as Array<{
    slug: string;
    label: string;
    prompt_suffix: string;
  }>;
}

export async function createGeneration(body: {
  business_id?: string | null;
  session_id: string;
  tool: CanvasTool;
  model: string;
  prompt?: string;
  params?: Record<string, unknown>;
  references?: ReferenceChipT[];
  parent_generation_id?: string | null;
}): Promise<Generation> {
  const res = await apiFetch(`/generations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 402) {
    const data = (await res.json()) as {
      detail?: { needed_cents: number; balance_cents: number };
    };
    const d = data.detail;
    throw new InsufficientCreditsError(d?.needed_cents ?? 0, d?.balance_cents ?? 0);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`createGeneration: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as Generation;
}

export async function getGeneration(id: string): Promise<Generation> {
  const res = await apiFetch(`/generations/${id}`);
  if (!res.ok) throw new Error(`getGeneration: ${res.status}`);
  return (await res.json()) as Generation;
}

export async function listGenerations(opts: {
  session_id?: string;
  tool?: CanvasTool;
  business_id?: string;
  favorited?: boolean;
  limit?: number;
}): Promise<Generation[]> {
  const params = new URLSearchParams();
  if (opts.session_id) params.set("session_id", opts.session_id);
  if (opts.tool) params.set("tool", opts.tool);
  if (opts.business_id) params.set("business_id", opts.business_id);
  if (opts.favorited !== undefined) params.set("favorited", String(opts.favorited));
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  const res = await apiFetch(`/generations${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`listGenerations: ${res.status}`);
  return (await res.json()) as Generation[];
}

export async function toggleFavoriteGeneration(id: string): Promise<Generation> {
  const res = await apiFetch(`/generations/${id}/favorite`, { method: "POST" });
  if (!res.ok) throw new Error(`toggleFavoriteGeneration: ${res.status}`);
  return (await res.json()) as Generation;
}

export async function runGenerationAction(
  id: string,
  body: {
    action: "animate" | "lipsync" | "edit" | "upscale" | "use_as_reference";
    prompt?: string;
    params?: Record<string, unknown>;
    model?: string;
  },
): Promise<Generation> {
  const res = await apiFetch(`/generations/${id}/action`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 402) {
    const data = (await res.json()) as {
      detail?: { needed_cents: number; balance_cents: number };
    };
    const d = data.detail;
    throw new InsufficientCreditsError(d?.needed_cents ?? 0, d?.balance_cents ?? 0);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`runGenerationAction: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as Generation;
}

export async function compareGenerations(body: {
  business_id?: string | null;
  session_id: string;
  tool: CanvasTool;
  models: string[];
  prompt: string;
  params?: Record<string, unknown>;
  references?: ReferenceChipT[];
}): Promise<Generation[]> {
  const res = await apiFetch(`/generations/compare`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 402) {
    const data = (await res.json()) as {
      detail?: { needed_cents: number; balance_cents: number };
    };
    const d = data.detail;
    throw new InsufficientCreditsError(d?.needed_cents ?? 0, d?.balance_cents ?? 0);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`compareGenerations: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as Generation[];
}

export async function listCharacters(businessId: string): Promise<CharacterT[]> {
  const res = await apiFetch(`/businesses/${businessId}/characters`);
  if (!res.ok) throw new Error(`listCharacters: ${res.status}`);
  return (await res.json()) as CharacterT[];
}

export async function createCharacter(
  businessId: string,
  body: { name: string; reference_image_urls: string[] },
): Promise<CharacterT> {
  const res = await apiFetch(`/businesses/${businessId}/characters`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createCharacter: ${res.status}`);
  return (await res.json()) as CharacterT;
}

export async function deleteCharacter(id: string): Promise<void> {
  const res = await apiFetch(`/characters/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deleteCharacter: ${res.status}`);
}

export async function listStyles(businessId: string): Promise<StyleT[]> {
  const res = await apiFetch(`/businesses/${businessId}/styles`);
  if (!res.ok) throw new Error(`listStyles: ${res.status}`);
  return (await res.json()) as StyleT[];
}

export async function createStyle(
  businessId: string,
  body: {
    name: string;
    reference_image_urls?: string[];
    palette?: Record<string, unknown>;
    notes?: string | null;
  },
): Promise<StyleT> {
  const res = await apiFetch(`/businesses/${businessId}/styles`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createStyle: ${res.status}`);
  return (await res.json()) as StyleT;
}

export async function deleteStyle(id: string): Promise<void> {
  const res = await apiFetch(`/styles/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deleteStyle: ${res.status}`);
}

export async function listPresets(tool?: CanvasTool): Promise<PresetT[]> {
  const path = tool ? `/users/me/presets?tool=${tool}` : `/users/me/presets`;
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`listPresets: ${res.status}`);
  return (await res.json()) as PresetT[];
}

export async function createPreset(body: {
  name: string;
  tool: CanvasTool;
  model: string;
  params?: Record<string, unknown>;
  prompt_template?: string | null;
}): Promise<PresetT> {
  const res = await apiFetch(`/users/me/presets`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createPreset: ${res.status}`);
  return (await res.json()) as PresetT;
}

export async function deletePreset(id: string): Promise<void> {
  const res = await apiFetch(`/presets/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deletePreset: ${res.status}`);
}

export async function getUsage(): Promise<UsageResponse> {
  const res = await apiFetch(`/users/me/usage`);
  if (!res.ok) throw new Error(`getUsage: ${res.status}`);
  return (await res.json()) as UsageResponse;
}

// ── Builder ───────────────────────────────────────────────────────

export type BuilderFramework = "next" | "vite" | "static" | "react_cra" | "other";
export type BuilderStatus = "draft" | "ready" | "published" | "error";
export type BuilderSourceType = "blank" | "import_github" | "import_zip";

export interface BuilderProject {
  id: string;
  user_id: string;
  business_id: string | null;
  name: string;
  slug: string;
  description: string | null;
  source_type: BuilderSourceType;
  source_url: string | null;
  framework: BuilderFramework;
  status: BuilderStatus;
  github_repo_url: string | null;
  published_url: string | null;
  custom_domain: string | null;
  current_version_id: string | null;
  previous_version_id: string | null;
  daily_spend_cents: number;
  daily_spend_cap_cents: number;
  created_at: string;
  updated_at: string;
}

export interface BuilderPlan {
  id: string;
  project_id: string;
  user_prompt: string;
  plain_plan: string;
  technical_plan: string;
  affected_areas: Array<{ label: string; rationale: string }>;
  risks: string | null;
  recommendation: string | null;
  file_hints: string[];
  model_used: string | null;
  status: "proposed" | "approved" | "rejected" | "applied" | "failed";
  applied_version_id: string | null;
  error: string | null;
  created_at: string;
}

export interface BuilderVersion {
  id: string;
  project_id: string;
  parent_version_id: string | null;
  label: string | null;
  change_summary_plain: string | null;
  change_summary_technical: string | null;
  commit_sha: string | null;
  created_at: string;
}

export interface BuilderFile {
  path: string;
  content: string;
  hash: string;
  binary_url: string | null;
}

export interface BuilderPreviewManifest {
  framework: BuilderFramework;
  dev_command: string[];
  files: Record<string, string>;
}

export interface BuilderVerifyReport {
  ok: boolean;
  checks: Array<{
    name: string;
    status: "ok" | "warn" | "fail";
    plain_english: string;
    detail: string | null;
  }>;
  warnings: number;
  errors: number;
}

export async function listBuilderProjects(): Promise<BuilderProject[]> {
  const res = await apiFetch(`/builder/projects`);
  if (!res.ok) throw new Error(`listBuilderProjects: ${res.status}`);
  return (await res.json()) as BuilderProject[];
}

export async function createBuilderProject(body: {
  name: string;
  description?: string;
  source_type?: BuilderSourceType;
  source_url?: string;
  template?: string;
  business_id?: string | null;
}): Promise<BuilderProject> {
  const res = await apiFetch(`/builder/projects`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`createBuilderProject: ${res.status} ${t.slice(0, 200)}`);
  }
  return (await res.json()) as BuilderProject;
}

export async function getBuilderProject(id: string): Promise<BuilderProject> {
  const res = await apiFetch(`/builder/projects/${id}`);
  if (!res.ok) throw new Error(`getBuilderProject: ${res.status}`);
  return (await res.json()) as BuilderProject;
}

export async function patchBuilderProject(
  id: string,
  body: Partial<
    Pick<BuilderProject, "name" | "description" | "custom_domain" | "daily_spend_cap_cents">
  >,
): Promise<BuilderProject> {
  const res = await apiFetch(`/builder/projects/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patchBuilderProject: ${res.status}`);
  return (await res.json()) as BuilderProject;
}

export async function deleteBuilderProject(id: string): Promise<void> {
  const res = await apiFetch(`/builder/projects/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deleteBuilderProject: ${res.status}`);
}

export async function listBuilderFiles(projectId: string): Promise<BuilderFile[]> {
  const res = await apiFetch(`/builder/projects/${projectId}/files`);
  if (!res.ok) throw new Error(`listBuilderFiles: ${res.status}`);
  return (await res.json()) as BuilderFile[];
}

export async function getBuilderPreviewManifest(
  projectId: string,
): Promise<BuilderPreviewManifest> {
  const res = await apiFetch(`/builder/projects/${projectId}/preview_manifest`);
  if (!res.ok) throw new Error(`getBuilderPreviewManifest: ${res.status}`);
  return (await res.json()) as BuilderPreviewManifest;
}

export async function proposeBuilderPlan(
  projectId: string,
  user_prompt: string,
): Promise<BuilderPlan> {
  const res = await apiFetch(`/builder/projects/${projectId}/plan`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ user_prompt }),
  });
  if (!res.ok) throw await apiErrorFromResponse(res, "proposeBuilderPlan");
  return (await res.json()) as BuilderPlan;
}

export async function listBuilderPlans(projectId: string): Promise<BuilderPlan[]> {
  const res = await apiFetch(`/builder/projects/${projectId}/plans`);
  if (!res.ok) throw new Error(`listBuilderPlans: ${res.status}`);
  return (await res.json()) as BuilderPlan[];
}

export async function approveBuilderPlan(planId: string): Promise<BuilderPlan> {
  const res = await apiFetch(`/builder/plans/${planId}/approve`, { method: "POST" });
  if (!res.ok) throw await apiErrorFromResponse(res, "approveBuilderPlan");
  return (await res.json()) as BuilderPlan;
}

export async function rejectBuilderPlan(planId: string): Promise<BuilderPlan> {
  const res = await apiFetch(`/builder/plans/${planId}/reject`, { method: "POST" });
  if (!res.ok) throw new Error(`rejectBuilderPlan: ${res.status}`);
  return (await res.json()) as BuilderPlan;
}

export async function undoBuilderProject(projectId: string): Promise<BuilderVersion | null> {
  const res = await apiFetch(`/builder/projects/${projectId}/undo`, { method: "POST" });
  if (!res.ok) throw new Error(`undoBuilderProject: ${res.status}`);
  return (await res.json()) as BuilderVersion | null;
}

export async function listBuilderVersions(projectId: string): Promise<BuilderVersion[]> {
  const res = await apiFetch(`/builder/projects/${projectId}/versions`);
  if (!res.ok) throw new Error(`listBuilderVersions: ${res.status}`);
  return (await res.json()) as BuilderVersion[];
}

export async function verifyBuilderProject(projectId: string): Promise<BuilderVerifyReport> {
  const res = await apiFetch(`/builder/projects/${projectId}/verify`);
  if (!res.ok) throw new Error(`verifyBuilderProject: ${res.status}`);
  return (await res.json()) as BuilderVerifyReport;
}

export interface BuilderPublishResponse {
  project_id: string;
  slug: string;
  published_url: string | null;
  status: string;
}

export async function publishBuilderProject(projectId: string): Promise<BuilderPublishResponse> {
  const res = await apiFetch(`/builder/projects/${projectId}/publish`, {
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`publishBuilderProject: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as BuilderPublishResponse;
}

export interface BuilderCustomDomainResponse {
  domain: string;
  record_type: string;
  host: string;
  target: string;
  status: string;
  guidance: string;
}

export async function setBuilderCustomDomain(
  projectId: string,
  domain: string,
): Promise<BuilderCustomDomainResponse> {
  const res = await apiFetch(`/builder/projects/${projectId}/custom_domain`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ domain }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`setBuilderCustomDomain: ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as BuilderCustomDomainResponse;
}
