import { mobileEnv } from "./env";
import { supabase } from "./supabase";

/**
 * Helm API client for mobile — mirrors apps/web/lib/api.ts surface but
 * uses buffered chat responses instead of SSE (RN's fetch doesn't expose
 * a ReadableStream API across all platforms yet). Streaming lands in
 * Session 12 via `react-native-sse` or an expo-polyfill.
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
// Chat — buffered. SSE streaming lands Session 12.
// ──────────────────────────────────────────────────────────

export interface ChatTurnResult {
  agentText: string;
  toolCalls: string[];
  approvals: {
    approval_id: string;
    approval_kind: string;
    summary: string;
    expires_at: string;
  }[];
  costCents: number;
  error?: string;
}

export async function sendChatTurn(message: string, businessId?: string): Promise<ChatTurnResult> {
  const env = mobileEnv();
  const res = await fetch(`${env.helmApiBase}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(await authHeader()),
    },
    body: JSON.stringify({ message, business_id: businessId ?? null }),
  });
  if (!res.ok) throw new Error(`chat ${res.status}: ${await res.text()}`);

  // Consume the whole SSE body as text, then parse events offline.
  // Gives us an end-of-turn snapshot without needing a streaming reader.
  const body = await res.text();
  const result: ChatTurnResult = {
    agentText: "",
    toolCalls: [],
    approvals: [],
    costCents: 0,
  };

  for (const frame of body.split("\n\n")) {
    for (const line of frame.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice("data: ".length));
        if (event.kind === "text_delta") {
          result.agentText += event.text ?? "";
        } else if (event.kind === "tool_call") {
          result.toolCalls.push(event.name);
        } else if (event.kind === "approval_requested") {
          result.approvals.push({
            approval_id: event.approval_id,
            approval_kind: event.approval_kind,
            summary: event.summary,
            expires_at: event.expires_at,
          });
        } else if (event.kind === "turn_cost") {
          result.costCents = event.cost_cents ?? 0;
        } else if (event.kind === "error") {
          result.error = `${event.reason}${event.detail ? `: ${event.detail}` : ""}`;
        }
      } catch {
        // Skip malformed frames — defensive.
      }
    }
  }
  return result;
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
}

export async function listApprovals(status?: Approval["status"]): Promise<Approval[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await apiFetch(`/approvals${qs}`);
  if (!res.ok) throw new Error(`listApprovals ${res.status}`);
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
  if (!res.ok) throw new Error(`respondToApproval ${res.status}: ${await res.text()}`);
  return res.json();
}
