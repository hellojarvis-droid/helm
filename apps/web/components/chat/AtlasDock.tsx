"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import { streamChat } from "@/lib/api";

// Contextual openers Atlas whispers when you land on each surface. These
// match the design handoff — the dock feels alive even before you talk.
const CONTEXTUAL: Record<string, string> = {
  overview: "Everything looks healthy. Cash runway holds at 11 months at current burn.",
  today: "Good morning. I've queued the daily brief — three items want your eyes.",
  businesses: "Your portfolio is nominal. Want me to surface any weak links?",
  approvals:
    "Pending approvals waiting on you. Tap one to open or ask me to explain the trade-offs.",
  safety: "Safety view. Kill switch is armed — one tap halts every agent in under a second.",
  billing: "Billing view. I can pull month-to-date LLM cost or walk you through plan changes.",
};

interface Msg {
  from: "agent" | "user";
  text: string;
}

interface Props {
  contextKey?: string;
}

export function AtlasDock({ contextKey = "overview" }: Props) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [messages, setMessages] = useState<Msg[]>(() => [
    {
      from: "agent",
      text: CONTEXTUAL[contextKey] ?? CONTEXTUAL.overview ?? "Atlas is on the bridge.",
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // On route change, whisper a new contextual line if we haven't already.
  useEffect(() => {
    const line = CONTEXTUAL[contextKey];
    if (!line) return;
    setMessages((prev) => {
      if (prev.some((m) => m.text === line)) return prev;
      return [...prev, { from: "agent", text: line }];
    });
  }, [contextKey]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, thinking]);

  // Abort any in-flight stream when the dock unmounts (e.g. nav to /chat).
  useEffect(() => () => abortRef.current?.abort(), []);

  async function send() {
    const text = input.trim();
    if (!text || thinking) return;
    setInput("");
    setMessages((m) => [...m, { from: "user", text }]);
    setThinking(true);
    const controller = new AbortController();
    abortRef.current = controller;

    let reply = "";
    try {
      for await (const ev of streamChat(text, undefined, controller.signal)) {
        if (ev.kind === "text_delta") {
          reply += ev.text;
        } else if (ev.kind === "done") {
          break;
        } else if (ev.kind === "error") {
          reply = reply || `(error: ${ev.reason})`;
          break;
        }
      }
    } catch (err) {
      reply = reply || (err instanceof Error ? err.message : "Network error");
    } finally {
      setThinking(false);
      if (reply) setMessages((m) => [...m, { from: "agent", text: reply }]);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          setCollapsed(false);
        }}
        className="fixed right-6 bottom-6 z-40 inline-flex items-center gap-2 px-4 py-3 rounded-full bg-ink text-paper border border-ink shadow-lg hover:bg-terracotta hover:border-terracotta transition-colors text-[13px]"
      >
        <span className="h-5.5 w-5.5 grid place-items-center rounded-full bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-[13px]">
          A
        </span>
        Ask Atlas
      </button>
    );
  }

  return (
    <div
      className={cn(
        "fixed right-6 bottom-6 z-40 w-[380px] flex flex-col bg-paper border border-rule rounded-lg shadow-lg overflow-hidden transition-all",
        collapsed ? "max-h-[56px]" : "max-h-[560px]",
      )}
    >
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center gap-2.5 px-3.5 py-3 border-b border-rule bg-paper-2 text-left"
      >
        <div className="relative h-7 w-7 grid place-items-center rounded-full bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-sm">
          A
          <span className="absolute -right-0.5 -bottom-0.5 h-2 w-2 rounded-full bg-sage border border-paper-2" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium leading-tight">Atlas</div>
          <div className="text-[11px] text-ink-3">CEO Agent · orchestrating the swarm</div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(false);
          }}
          className="h-6 w-6 grid place-items-center rounded-sm text-ink-3 hover:bg-sand hover:text-ink"
          aria-label="Close Atlas"
        >
          <Icon name="close" size={12} />
        </button>
      </button>

      {!collapsed && (
        <>
          <div
            ref={bodyRef}
            className="flex-1 overflow-y-auto scroll-paper px-4 py-4 flex flex-col gap-3 bg-paper"
          >
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn(
                  "max-w-[82%] px-3 py-2.5 rounded-[14px] text-[13.5px] leading-[1.45]",
                  m.from === "agent"
                    ? "bg-sand text-ink rounded-bl-[4px] self-start"
                    : "bg-ink text-paper rounded-br-[4px] self-end",
                )}
              >
                {m.text}
              </div>
            ))}
            {thinking && (
              <div className="self-start max-w-[82%] px-3 py-2.5 rounded-[14px] rounded-bl-[4px] bg-sand text-ink-3 text-[13px] opacity-80">
                <span className="typing">
                  <span>.</span>
                  <span>.</span>
                  <span>.</span>
                </span>
                {" "}consulting the swarm
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
            className="flex gap-2 p-2.5 border-t border-rule bg-paper-2"
          >
            <input
              className="flex-1 rounded-sm border border-rule bg-paper px-3 py-2 text-[13px] text-ink placeholder:text-ink-3 focus:outline-none focus:border-ink-2"
              placeholder="Ask Atlas to delegate, plan, or explain…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={thinking}
            />
            <button
              type="submit"
              disabled={thinking || input.trim().length === 0}
              className="inline-flex items-center justify-center h-9 px-3 rounded-sm bg-ink text-paper border border-ink hover:bg-terracotta hover:border-terracotta transition-colors disabled:opacity-50"
              aria-label="Send"
            >
              <Icon name="send" size={12} />
            </button>
          </form>
        </>
      )}
    </div>
  );
}
