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
