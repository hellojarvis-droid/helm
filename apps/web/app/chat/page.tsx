"use client";

import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ApprovalCard } from "@/components/chat/ApprovalCard";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  apiFetch,
  getChatHistory,
  type Business,
  type ChatHistoryItem,
  listBusinesses,
  streamChat,
  type ChatEvent,
} from "@/lib/api";

type TurnPart =
  | { kind: "user"; text: string }
  | { kind: "agent"; text: string; toolCalls: string[]; costCents: number }
  | { kind: "tool"; name: string; ok: boolean }
  | { kind: "approval"; event: Extract<ChatEvent, { kind: "approval_requested" }> };

export default function ChatPage() {
  const [parts, setParts] = useState<TurnPart[]>([]);
  const [pending, setPending] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [scopedBizId, setScopedBizId] = useState<string | undefined>(undefined);
  const [hydrated, setHydrated] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    listBusinesses()
      .then((rows) => {
        if (active) setBusinesses(rows);
      })
      .catch(() => {
        // Silent: business picker is a nice-to-have. Without the list,
        // the user just gets the unscoped CEO conversation.
      });
    getChatHistory()
      .then((history) => {
        if (!active) return;
        const restored = history.items
          .map(historyItemToPart)
          .filter((p): p is TurnPart => p !== null);
        setParts((current) => (current.length ? current : restored));
      })
      .catch(() => {
        // Silent: a fresh account or transient auth issue should not block chat.
      })
      .finally(() => {
        if (active) setHydrated(true);
      });
    return () => {
      active = false;
    };
  }, []);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setError(null);
    setPending("");
    setParts((p) => [...p, { kind: "user", text }]);

    const controller = new AbortController();
    abortRef.current = controller;

    let acc = "";
    let toolCalls: string[] = [];
    let costCents = 0;
    try {
      for await (const ev of streamChat(text, scopedBizId, controller.signal)) {
        if (ev.kind === "text_delta") {
          acc += ev.text;
          setPending(acc);
        } else if (ev.kind === "tool_call") {
          toolCalls = [...toolCalls, ev.name];
          setParts((p) => [...p, { kind: "tool", name: ev.name, ok: true }]);
        } else if (ev.kind === "tool_result") {
          setParts((p) => [...p, { kind: "tool", name: ev.name, ok: !ev.is_error }]);
        } else if (ev.kind === "approval_requested") {
          setParts((p) => [...p, { kind: "approval", event: ev }]);
        } else if (ev.kind === "turn_cost") {
          costCents = ev.cost_cents;
        } else if (ev.kind === "done") {
          if (acc) setParts((p) => [...p, { kind: "agent", text: acc, toolCalls, costCents }]);
          setPending("");
        } else if (ev.kind === "error") {
          setError(`${ev.reason}${ev.detail ? `: ${ev.detail}` : ""}`);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function respond(
    approvalId: string,
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) {
    try {
      const res = await apiFetch(`/approvals/${approvalId}/respond`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, modifications: modifications ?? null }),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = (await res.json()) as {
        cap_raise?: { changed?: boolean; new_cap_cents?: number } | null;
      };
      let label = `approval:${status}`;
      if (status === "modified" && modifications?.raise_weekly_cap) {
        const cap = body.cap_raise;
        const newCap =
          cap && cap.changed && typeof cap.new_cap_cents === "number"
            ? `$${(cap.new_cap_cents / 100).toFixed(0)}`
            : null;
        label = newCap ? `approval:approved · cap raised to ${newCap}` : "approval:approved";
      }
      setParts((p) =>
        p.map((part) =>
          part.kind === "approval" && part.event.approval_id === approvalId
            ? { kind: "tool", name: label, ok: true }
            : part,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <AppShell breadcrumbs={["Helm", "Chat"]}>
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto scroll-paper">
          <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-5 sm:px-8 sm:py-8">
            {hydrated && parts.length === 0 && !pending && (
              <EmptyChat
                onPick={(prompt) => setInput(prompt)}
                hasBusinesses={businesses.length > 0}
              />
            )}
            {!hydrated && <p className="text-sm text-ink-3">Loading Atlas thread…</p>}
            {parts.map((part, i) => (
              <TurnPartView key={i} part={part} onApproval={respond} />
            ))}
            {pending && (
              <div className="max-w-2xl text-[15px] leading-relaxed whitespace-pre-wrap text-ink">
                {pending}
                <span className="inline-block w-1 h-4 bg-ink/60 align-middle ml-0.5 animate-pulse" />
              </div>
            )}
            {error && <div className="text-sm text-rose-2">{error}</div>}
          </div>
        </div>

        <div className="border-t border-rule bg-paper-2">
          <div className="max-w-3xl mx-auto px-4 py-4 space-y-3 sm:px-8">
            {businesses.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                <BusinessPill
                  label="All businesses"
                  active={scopedBizId === undefined}
                  onClick={() => setScopedBizId(undefined)}
                />
                {businesses.map((b) => (
                  <BusinessPill
                    key={b.id}
                    label={b.name}
                    active={scopedBizId === b.id}
                    onClick={() => setScopedBizId(b.id)}
                  />
                ))}
              </div>
            ) : null}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
              className="flex flex-col gap-2 sm:flex-row"
            >
              <input
                className="flex-1 rounded-sm border border-rule bg-paper px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-3 focus:outline-none focus:border-ink-2 disabled:opacity-50"
                placeholder={busy ? "Atlas is thinking…" : "Tell the CEO Agent what to do"}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={busy}
                autoFocus
              />
              <Button type="submit" disabled={busy || input.trim().length === 0} size="lg">
                <Icon name="send" size={13} /> Send
              </Button>
            </form>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

const STARTER_PROMPTS_NEW = [
  "Find me a proven candle business idea I could launch this week.",
  "What are you good for? Walk me through what you can do.",
  "I want to spin up a SaaS — start with the idea, then the brand.",
];
const STARTER_PROMPTS_RETURNING = [
  "How are my businesses doing this week?",
  "Find a fresh growth opportunity for my best-performing business.",
  "Run a Sunday review — give me wins, watches, and three recommendations.",
];

function EmptyChat({
  onPick,
  hasBusinesses,
}: {
  onPick: (prompt: string) => void;
  hasBusinesses: boolean;
}) {
  const prompts = hasBusinesses ? STARTER_PROMPTS_RETURNING : STARTER_PROMPTS_NEW;
  return (
    <div className="mt-10 space-y-7">
      <div className="text-center space-y-3">
        <div className="mx-auto h-14 w-14 grid place-items-center rounded-full bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-[28px] leading-none">
          A
        </div>
        <h1 className="font-serif text-[36px] leading-tight tracking-tightest">
          {hasBusinesses ? "What's on your mind?" : "Tell Atlas what to build."}
        </h1>
        <p className="text-sm text-ink-3 max-w-md mx-auto">
          {hasBusinesses
            ? "Ask Atlas anything about your portfolio — or pick a starter."
            : "Atlas delegates to the right specialist and comes back with a plan."}
        </p>
      </div>
      <div className="grid gap-2 max-w-xl mx-auto">
        {prompts.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPick(p)}
            className="text-left p-4 rounded-md border border-rule bg-paper hover:bg-sand transition-colors"
          >
            <span className="text-sm text-ink">{p}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function BusinessPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-3 py-1 rounded-full text-xs font-medium transition-colors",
        active
          ? "bg-ink text-paper"
          : "bg-paper text-ink-2 border border-rule hover:bg-sand hover:text-ink",
      )}
    >
      {label}
    </button>
  );
}

function historyItemToPart(item: ChatHistoryItem): TurnPart | null {
  if (item.kind === "message.user" && item.text) {
    return { kind: "user", text: item.text };
  }
  if (item.kind === "message.agent" && item.text) {
    return { kind: "agent", text: item.text, toolCalls: [], costCents: 0 };
  }
  if (item.kind === "tool_call") {
    const name = typeof item.payload.name === "string" ? item.payload.name : "tool";
    return { kind: "tool", name, ok: true };
  }
  if (item.kind === "tool_result") {
    const name = typeof item.payload.name === "string" ? item.payload.name : "tool";
    return { kind: "tool", name, ok: item.payload.is_error !== true };
  }
  if (item.kind === "approval_requested" && item.approval?.approval_id) {
    const details =
      typeof item.payload.details === "object" && item.payload.details !== null
        ? (item.payload.details as Record<string, unknown>)
        : undefined;
    return {
      kind: "approval",
      event: {
        kind: "approval_requested",
        approval_id: item.approval.approval_id,
        approval_kind: item.approval.kind ?? "other",
        summary: item.approval.summary ?? item.text ?? "Approval requested",
        details,
        business_id: item.business_id ?? "",
        expires_at:
          typeof item.payload.expires_at === "string" ? item.payload.expires_at : item.created_at,
      },
    };
  }
  if (
    item.kind === "approval_approved" ||
    item.kind === "approval_denied" ||
    item.kind === "approval_modified"
  ) {
    return {
      kind: "tool",
      name: item.kind.replace("approval_", "approval:"),
      ok: item.kind !== "approval_denied",
    };
  }
  return null;
}

function TurnPartView({
  part,
  onApproval,
}: {
  part: TurnPart;
  onApproval: (
    approvalId: string,
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) => void;
}) {
  if (part.kind === "user") {
    return (
      <div className="flex justify-end">
        <div className="rounded-[14px] rounded-br-[4px] bg-ink text-paper px-4 py-2.5 text-[14px] leading-relaxed max-w-2xl">
          {part.text}
        </div>
      </div>
    );
  }
  if (part.kind === "agent") {
    return (
      <div className="max-w-2xl">
        <div className="rounded-[14px] rounded-bl-[4px] bg-sand text-ink px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap">
          {part.text}
        </div>
        {part.toolCalls.length || part.costCents > 0 ? (
          <div className="mt-1.5 ml-1 flex flex-wrap gap-3 text-[11px] text-ink-3 font-mono">
            {part.toolCalls.length ? <span>tools: {part.toolCalls.join(", ")}</span> : null}
            {part.costCents > 0 ? <span>cost: {part.costCents}¢</span> : null}
          </div>
        ) : null}
      </div>
    );
  }
  if (part.kind === "tool") {
    const color = part.ok ? "text-ink-3" : "text-rose-2";
    return (
      <div className={`text-xs ${color} font-mono ml-1`}>
        {part.ok ? "✓" : "✗"} {part.name}
      </div>
    );
  }
  const ev = part.event;
  return (
    <ApprovalCard
      approval_id={ev.approval_id}
      approval_kind={ev.approval_kind}
      summary={ev.summary}
      expires_at={ev.expires_at}
      details={ev.details}
      onRespond={(status, modifications) => onApproval(ev.approval_id, status, modifications)}
    />
  );
}
