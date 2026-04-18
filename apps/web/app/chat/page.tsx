"use client";

import { useRef, useState } from "react";
import { ApprovalCard } from "@/components/chat/ApprovalCard";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { apiFetch, streamChat, type ChatEvent } from "@/lib/api";

type TurnPart =
  | { kind: "user"; text: string }
  | { kind: "agent"; text: string }
  | { kind: "tool"; name: string; ok: boolean }
  | { kind: "approval"; event: Extract<ChatEvent, { kind: "approval_requested" }> };

export default function ChatPage() {
  const [parts, setParts] = useState<TurnPart[]>([]);
  const [pending, setPending] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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
    try {
      for await (const ev of streamChat(text, undefined, controller.signal)) {
        if (ev.kind === "text_delta") {
          acc += ev.text;
          setPending(acc);
        } else if (ev.kind === "tool_call") {
          setParts((p) => [...p, { kind: "tool", name: ev.name, ok: true }]);
        } else if (ev.kind === "tool_result") {
          setParts((p) => [...p, { kind: "tool", name: ev.name, ok: !ev.is_error }]);
        } else if (ev.kind === "approval_requested") {
          setParts((p) => [...p, { kind: "approval", event: ev }]);
        } else if (ev.kind === "done") {
          if (acc) setParts((p) => [...p, { kind: "agent", text: acc }]);
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

  async function respond(approvalId: string, status: "approved" | "denied") {
    try {
      const res = await apiFetch(`/approvals/${approvalId}/respond`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(await res.text());
      // Replace the approval card with a compact status line.
      setParts((p) =>
        p.map((part) =>
          part.kind === "approval" && part.event.approval_id === approvalId
            ? { kind: "tool", name: `approval:${status}`, ok: true }
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
          <div className="text-iron text-sm mt-16 text-center">
            Start a conversation. The CEO Agent is listening.
          </div>
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

      <footer className="border-t border-iron/20 px-6 py-4 max-w-3xl w-full mx-auto">
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

function TurnPartView({
  part,
  onApproval,
}: {
  part: TurnPart;
  onApproval: (approvalId: string, status: "approved" | "denied") => void;
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
    return <div className="text-sm leading-relaxed whitespace-pre-wrap max-w-2xl">{part.text}</div>;
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
      onRespond={(status) => onApproval(ev.approval_id, status)}
    />
  );
}
