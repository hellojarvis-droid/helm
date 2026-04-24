"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { type AgentEvent, listEvents } from "@/lib/api";

const EVENT_BADGE: Record<string, { label: string; className: string }> = {
  "message.user": { label: "user", className: "bg-ink text-paper" },
  "message.agent": { label: "agent", className: "bg-haze text-ink border border-iron/20" },
  tool_call: { label: "tool", className: "bg-accent/10 text-accent border border-accent/30" },
  tool_result: { label: "result", className: "bg-accent/10 text-accent border border-accent/30" },
  approval_requested: {
    label: "approval",
    className: "bg-warning/10 text-warning border border-warning/40",
  },
  approval_approved: {
    label: "approved",
    className: "bg-success/10 text-success border border-success/40",
  },
  approval_modified: {
    label: "modified",
    className: "bg-accent/10 text-accent border border-accent/40",
  },
  approval_denied: {
    label: "denied",
    className: "bg-danger/10 text-danger border border-danger/40",
  },
  spend_intent: {
    label: "spend intent",
    className: "bg-haze text-iron border border-iron/20",
  },
  spend_authorized: {
    label: "spend",
    className: "bg-success/10 text-success border border-success/40",
  },
  spend_declined: {
    label: "spend declined",
    className: "bg-danger/10 text-danger border border-danger/40",
  },
  revenue_received: {
    label: "revenue",
    className: "bg-success text-paper",
  },
  specialist_completed: {
    label: "specialist",
    className: "bg-haze text-ink border border-iron/20",
  },
  computer_use_requested: {
    label: "computer use",
    className: "bg-ink text-paper",
  },
  kill_switch_activated: {
    label: "kill switch",
    className: "bg-danger text-paper",
  },
  error: { label: "error", className: "bg-danger/10 text-danger border border-danger/40" },
};

const PAGE_SIZE = 30;

export function ActivityFeed({ businessId }: { businessId: string }) {
  const [events, setEvents] = useState<AgentEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reachedEnd, setReachedEnd] = useState(false);

  const load = useCallback(
    async (beforeId?: number) => {
      setLoading(true);
      setError(null);
      try {
        const rows = await listEvents(businessId, { limit: PAGE_SIZE, beforeId });
        if (rows.length < PAGE_SIZE) setReachedEnd(true);
        // Only append when the caller is paginating (beforeId defined). Initial
        // loads replace — React strict mode runs effects twice in dev, and
        // without this guard the second invocation duplicates every row.
        // Defensive dedupe as well so any stray overlap (Fast Refresh replay,
        // retries, or server race) never leaves two rows with the same key.
        setEvents((prev) => {
          const merged =
            beforeId !== undefined && prev ? [...prev, ...rows] : rows;
          const seen = new Set<number>();
          return merged.filter((r) => {
            if (seen.has(r.id)) return false;
            seen.add(r.id);
            return true;
          });
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [businessId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (events === null) {
    return <p className="text-sm text-iron">Loading activity…</p>;
  }

  if (error && events.length === 0) {
    return <p className="text-sm text-danger">{error}</p>;
  }

  if (events.length === 0) {
    return (
      <p className="text-sm text-iron">
        No activity yet. Events appear here as soon as the CEO Agent starts working.
      </p>
    );
  }

  const oldestId = events[events.length - 1]?.id;

  return (
    <div className="space-y-3">
      <ol className="space-y-2">
        {events.map((ev) => (
          <EventRow key={ev.id} ev={ev} />
        ))}
      </ol>
      {error ? <p className="text-xs text-danger">{error}</p> : null}
      {!reachedEnd ? (
        <button
          onClick={() => oldestId && void load(oldestId)}
          disabled={loading}
          className="text-sm text-iron hover:text-ink dark:hover:text-paper disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load older"}
        </button>
      ) : (
        <p className="text-xs text-iron">— end of log —</p>
      )}
    </div>
  );
}

function EventRow({ ev }: { ev: AgentEvent }) {
  const badge = EVENT_BADGE[ev.event_type] ?? {
    label: ev.event_type,
    className: "bg-haze text-iron border border-iron/20",
  };
  const when = new Date(ev.created_at).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
  const summary = summarize(ev);
  return (
    <li className="flex items-start gap-3 py-2 border-b border-iron/10 last:border-b-0">
      <span
        className={cn(
          "text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded shrink-0",
          badge.className,
        )}
      >
        {badge.label}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm break-words">{summary}</div>
        <div className="text-xs text-iron mt-0.5 flex gap-3">
          <span>{ev.agent_name}</span>
          <span>{when}</span>
          {ev.cost_cents > 0 ? <span>{ev.cost_cents}¢</span> : null}
        </div>
      </div>
    </li>
  );
}

function summarize(ev: AgentEvent): string {
  const p = ev.payload;
  switch (ev.event_type) {
    case "message.user":
    case "message.agent":
      return typeof p.text === "string" ? p.text : JSON.stringify(p);
    case "tool_call":
      return `Called ${stringOr(p.name, "tool")}`;
    case "tool_result":
      return `${stringOr(p.name, "tool")} → ${p.is_error ? "error" : "ok"}`;
    case "approval_requested":
      return `Requested approval: ${stringOr(p.summary, stringOr(p.kind, "—"))}`;
    case "approval_approved":
    case "approval_denied":
      return `${stringOr(p.kind, "approval")} ${ev.event_type === "approval_approved" ? "approved" : "denied"}`;
    case "approval_modified": {
      const cap = p.cap_raise as Record<string, unknown> | undefined;
      if (cap && cap.changed && typeof cap.new_cap_cents === "number") {
        return `${stringOr(p.kind, "approval")} approved — weekly cap raised to $${((cap.new_cap_cents as number) / 100).toFixed(0)}`;
      }
      return `${stringOr(p.kind, "approval")} modified`;
    }
    case "spend_intent":
      return `Intent: $${((Number(p.amount_cents) || 0) / 100).toFixed(2)} to ${stringOr(p.merchant_hint, "?")} · ${stringOr(p.purpose, "")}`.trim();
    case "spend_authorized":
      return `Spend authorized: $${((Number(p.amount_cents) || 0) / 100).toFixed(2)} to ${stringOr(p.merchant_name, stringOr(p.merchant_category, "?"))}`;
    case "spend_declined":
      return `Declined: ${stringOr(p.reason, "spend policy")}`;
    case "revenue_received":
      return `Revenue: $${((Number(p.amount_cents) || 0) / 100).toFixed(2)}`;
    case "specialist_completed":
      return `${stringOr(p.name, "specialist")} → ${stringOr(p.status, "ok")}`;
    case "computer_use_requested":
      return `Computer use queued: ${stringOr(p.task, "—")} (${stringOr(p.app_hint, "no app hint")})`;
    case "kill_switch_activated":
      return "Kill switch activated — all agents halted.";
    case "error":
      return stringOr(p.message, stringOr(p.detail, "error"));
    default:
      return JSON.stringify(p);
  }
}

function stringOr(v: unknown, fallback: string): string {
  return typeof v === "string" || typeof v === "number" ? String(v) : fallback;
}
