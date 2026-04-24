"use client";

import { useCallback, useState } from "react";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import { type ApprovalTrace, getApprovalTrace } from "@/lib/api";

interface Props {
  approvalId: string;
  /** Subtle ("Why?") for list cards, prominent ("Why did Atlas ask?") for detail. */
  variant?: "subtle" | "prominent";
}

// Why? — expandable explanation anchored to the approval_requested event.
// Lazy-fetches the trace on first open, caches in component state, and
// renders the chain as a vertical timeline (user msg → Atlas reasoning →
// tool calls → specialist completions → this approval).
export function ApprovalWhy({ approvalId, variant = "subtle" }: Props) {
  const [open, setOpen] = useState(false);
  const [trace, setTrace] = useState<ApprovalTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = useCallback(async () => {
    const next = !open;
    setOpen(next);
    if (next && !trace && !loading) {
      setLoading(true);
      try {
        setTrace(await getApprovalTrace(approvalId));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    }
  }, [approvalId, open, trace, loading]);

  const label = variant === "prominent" ? "Why did Atlas ask?" : "Why?";

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={toggle}
        className={cn(
          "inline-flex items-center gap-1.5 text-[12px] text-ink-3 hover:text-ink",
          variant === "prominent" && "text-[13px] text-terracotta-2 hover:text-terracotta",
        )}
      >
        <Icon name="sparkle" size={12} />
        {label}
        <span className="opacity-60">{open ? "↑" : "↓"}</span>
      </button>

      {open && (
        <div className="mt-3 rounded-sm border border-rule bg-paper-2 p-4">
          {loading && <div className="text-xs text-ink-3">Loading the reasoning chain…</div>}
          {error && <div className="text-xs text-rose-2">{error}</div>}
          {trace && trace.events.length === 0 && (
            <div className="text-xs text-ink-3">
              No prior events found — this approval was created directly by the launch workflow.
            </div>
          )}
          {trace && trace.events.length > 0 && (
            <>
              <ol className="space-y-3">
                {trace.events.map((ev) => (
                  <TraceRow key={ev.id} ev={ev} />
                ))}
              </ol>
              {trace.total_cost_cents > 0 && (
                <div className="mt-3 pt-3 border-t border-rule text-[11px] text-ink-3 font-mono">
                  Reasoning compute: ${(trace.total_cost_cents / 100).toFixed(2)}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function TraceRow({
  ev,
}: {
  ev: ApprovalTrace["events"][number];
}) {
  const who = prettyAgent(ev.agent_name);
  const tone = toneFor(ev.event_type);
  return (
    <li className="flex gap-3">
      <div
        className={cn(
          "shrink-0 h-6 w-6 grid place-items-center rounded-full text-[11px]",
          tone === "user"
            ? "bg-ink text-paper"
            : tone === "agent"
              ? "bg-gradient-to-br from-terracotta to-amber text-paper font-serif"
              : tone === "tool"
                ? "bg-sand text-ink-2"
                : "bg-sage-soft text-sage-2",
        )}
      >
        {tone === "user" ? "Y" : tone === "agent" ? who[0] : tone === "tool" ? "⚒" : "✓"}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[11px] text-ink-3 font-mono">
          {who} · {new Date(ev.created_at).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
        <div className="text-[13px] text-ink-2 leading-snug mt-0.5">{summarize(ev)}</div>
      </div>
    </li>
  );
}

function prettyAgent(name: string): string {
  const MAP: Record<string, string> = {
    ceo_agent: "Atlas",
    creative_director: "Creative Director",
    product_builder: "Product Builder",
    ads_operator: "Ads Operator",
    growth_analyst: "Growth Analyst",
    social_engagement: "Social Engagement",
    customer_service: "Customer Service",
    finance_ops: "Finance Ops",
    idea_scout: "Idea Scout",
    launch_workflow: "Launch workflow",
    user: "You",
  };
  return MAP[name] ?? name;
}

function toneFor(eventType: string): "user" | "agent" | "tool" | "result" {
  if (eventType === "message.user") return "user";
  if (eventType === "message.agent") return "agent";
  if (eventType === "tool_call") return "tool";
  return "result";
}

function summarize(ev: ApprovalTrace["events"][number]): string {
  const p = ev.payload ?? {};
  switch (ev.event_type) {
    case "message.user":
      return typeof p.text === "string" ? p.text : "(empty message)";
    case "message.agent": {
      const t = typeof p.text === "string" ? p.text : "";
      return t.length > 260 ? t.slice(0, 260) + "…" : t;
    }
    case "tool_call":
      return `Called tool ${String(p.name ?? "")} ${summarizeArgs(p.input)}`;
    case "tool_result":
      return `${String(p.name ?? "")} → ${p.is_error ? "error" : "ok"}`;
    case "specialist_completed":
      return `Specialist ${String(p.specialist ?? ev.agent_name)} completed: ${String(p.summary_preview ?? "")}`;
    case "approval_requested":
      return `Requested this approval: ${String(p.summary ?? "")}`;
    case "launch_step_completed":
      return `Completed launch step: ${String(p.step ?? "")}`;
    case "launch_step_skipped":
      return `Skipped launch step: ${String(p.step ?? "")} — ${
        p.output && typeof (p.output as Record<string, unknown>).reason === "string"
          ? String((p.output as Record<string, unknown>).reason)
          : ""
      }`;
    case "launch_step_failed":
      return `Launch step failed: ${String(p.step ?? "")} — ${String(p.error ?? "")}`;
    default:
      return ev.event_type;
  }
}

function summarizeArgs(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  const entries = Object.entries(args as Record<string, unknown>).slice(0, 2);
  if (entries.length === 0) return "";
  const brief = entries
    .map(([k, v]) => `${k}=${typeof v === "string" ? v.slice(0, 40) : JSON.stringify(v).slice(0, 40)}`)
    .join(", ");
  return `(${brief})`;
}
