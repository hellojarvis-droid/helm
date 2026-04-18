"use client";

import { useEffect, useRef, useState } from "react";
import { ApprovalCard } from "@/components/chat/ApprovalCard";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { apiFetch, type Business, listBusinesses, streamChat, type ChatEvent } from "@/lib/api";

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
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listBusinesses()
      .then(setBusinesses)
      .catch(() => {
        // Silent: business picker is a nice-to-have. Without the list,
        // the user just gets the unscoped CEO conversation.
      });
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
    <div className="min-h-screen flex flex-col">
      <Nav />

      <main className="flex-1 max-w-3xl w-full mx-auto px-6 py-6 flex flex-col gap-4 overflow-y-auto">
        {parts.length === 0 && !pending && (
          <EmptyChat onPick={(prompt) => setInput(prompt)} hasBusinesses={businesses.length > 0} />
        )}
        {parts.map((part, i) => (
          <TurnPartView key={i} part={part} onApproval={respond} />
        ))}
        {pending && (
          <div className="text-sm leading-relaxed whitespace-pre-wrap">
            {pending}
            <span className="inline-block w-1 h-4 bg-ink/60 dark:bg-paper/60 align-middle ml-0.5 animate-pulse" />
          </div>
        )}
        {error && <div className="text-sm text-danger">{error}</div>}
      </main>

      <footer className="border-t border-iron/20 px-6 py-4 max-w-3xl w-full mx-auto space-y-3">
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
          className="flex gap-2"
        >
          <input
            className="flex-1 rounded-md border border-iron/30 bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/60"
            placeholder={busy ? "working…" : "Tell the CEO Agent what to do"}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
            autoFocus
          />
          <Button type="submit" disabled={busy || input.trim().length === 0}>
            Send
          </Button>
        </form>
      </footer>
    </div>
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
    <div className="mt-16 space-y-6">
      <div className="text-center">
        <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-2">
          {hasBusinesses ? "Where to next" : "Welcome to Helm"}
        </div>
        <p className="text-sm text-iron">
          {hasBusinesses
            ? "Ask the CEO Agent anything — or pick a starter."
            : "Tell the CEO Agent what you want to build. It delegates to the right specialist."}
        </p>
      </div>
      <div className="grid gap-2 max-w-xl mx-auto">
        {prompts.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPick(p)}
            className="text-left p-4 rounded-lg border border-iron/20 bg-haze/40 dark:bg-ink/20 hover:border-accent/60 transition-colors"
          >
            <span className="text-sm">{p}</span>
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
          ? "bg-ink text-paper dark:bg-paper dark:text-ink"
          : "bg-haze text-iron border border-iron/20 hover:text-ink",
      )}
    >
      {label}
    </button>
  );
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
        <div className="rounded-lg bg-ink text-paper dark:bg-paper dark:text-ink px-4 py-2 text-sm max-w-2xl">
          {part.text}
        </div>
      </div>
    );
  }
  if (part.kind === "agent") {
    return (
      <div className="max-w-2xl">
        <div className="text-sm leading-relaxed whitespace-pre-wrap">{part.text}</div>
        {part.toolCalls.length || part.costCents > 0 ? (
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-iron font-mono">
            {part.toolCalls.length ? <span>tools: {part.toolCalls.join(", ")}</span> : null}
            {part.costCents > 0 ? <span>cost: {part.costCents}¢</span> : null}
          </div>
        ) : null}
      </div>
    );
  }
  if (part.kind === "tool") {
    const color = part.ok ? "text-iron" : "text-danger";
    return (
      <div className={`text-xs ${color} font-mono`}>
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
