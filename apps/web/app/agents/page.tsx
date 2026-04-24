"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import { type AgentEvent, listAllEvents } from "@/lib/api";

// The eight specialists Helm ships with. Matches the registry in the API
// plus Atlas (the orchestrator — its events are tagged ceo_agent).
const SPECIALISTS: { name: string; display: string; role: string }[] = [
  { name: "ceo_agent", display: "Atlas", role: "CEO · Orchestrator" },
  { name: "creative_director", display: "Creative Director", role: "Brand, copy, visuals" },
  { name: "product_builder", display: "Product Builder", role: "Storefronts, SKUs, domains" },
  { name: "ads_operator", display: "Ads Operator", role: "Paid media across channels" },
  { name: "growth_analyst", display: "Growth Analyst", role: "Weekly reviews, anomalies" },
  { name: "social_engagement", display: "Social Engagement", role: "Comments, DMs, replies" },
  { name: "customer_service", display: "Customer Service", role: "Tickets, refunds, orders" },
  { name: "finance_ops", display: "Finance Ops", role: "Reconciliation, P&L, tax" },
  { name: "idea_scout", display: "Idea Scout", role: "Concepts, trend research" },
];

type Status = "active" | "busy" | "idle";

interface SpecialistState {
  name: string;
  display: string;
  role: string;
  status: Status;
  lastEvent: AgentEvent | null;
  lastTask: string | null;
  eventsLast24h: number;
}

const POLL_MS = 15_000;

export default function AgentsPage() {
  const [states, setStates] = useState<SpecialistState[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const events = await listAllEvents({ limit: 200 });
        if (cancelled) return;
        setStates(aggregate(events));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    void tick();
    const iv = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, []);

  return (
    <AppShell breadcrumbs={["Helm", "Agents"]}>
      <div className="px-10 pt-8 pb-20 max-w-5xl">
        <header className="mb-7">
          <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
            Agent Swarm
          </h1>
          <p className="text-sm text-ink-3 max-w-prose">
            Every specialist Atlas has on the bench. Status reflects what each has done in the
            last 24 hours — tap a card to see their event stream.
          </p>
        </header>

        {error && (
          <div className="mb-5 rounded-md border border-rose-2/50 bg-rose-soft/50 p-4 text-sm text-rose-2">
            {error}
          </div>
        )}

        {states === null ? (
          <p className="text-sm text-ink-3">Loading…</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {states.map((s) => (
              <AgentCard key={s.name} state={s} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function AgentCard({ state }: { state: SpecialistState }) {
  const { display, role, status, lastEvent, lastTask, eventsLast24h } = state;
  return (
    <Link
      href={`/events?agent_name=${encodeURIComponent(state.name)}`}
      className="block rounded-md border border-rule bg-paper p-5 hover:bg-sand transition-colors"
    >
      <div className="flex items-start gap-3 mb-3">
        <div
          className={cn(
            "h-10 w-10 grid place-items-center rounded-full text-paper font-serif text-base",
            status === "active"
              ? "bg-gradient-to-br from-sage to-terracotta"
              : status === "busy"
                ? "bg-gradient-to-br from-amber to-terracotta"
                : "bg-gradient-to-br from-sand-2 to-ink-3",
          )}
        >
          {display[0]}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[14px] font-medium">{display}</div>
          <div className="text-[11px] text-ink-3">{role}</div>
        </div>
        <span
          className={cn(
            "chip",
            status === "active" ? "chip-sage" : status === "busy" ? "chip-amber" : "",
          )}
        >
          {status}
        </span>
      </div>
      <div className="text-[12px] text-ink-2 leading-relaxed line-clamp-2 min-h-[32px]">
        {lastTask ?? "No activity in the last 24 hours."}
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px] text-ink-3">
        <span>
          <span className="font-mono">{eventsLast24h}</span> events · 24h
        </span>
        {lastEvent && (
          <span className="font-mono">
            {new Date(lastEvent.created_at).toLocaleString(undefined, {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        )}
      </div>
    </Link>
  );
}

function aggregate(events: AgentEvent[]): SpecialistState[] {
  const now = Date.now();
  const cutoff = now - 24 * 60 * 60 * 1000;
  return SPECIALISTS.map(({ name, display, role }) => {
    const forAgent = events.filter((e) => e.agent_name === name);
    const recent = forAgent.filter((e) => new Date(e.created_at).getTime() >= cutoff);
    const lastEvent = forAgent[0] ?? null;
    const lastTask = lastEvent ? summarize(lastEvent) : null;
    const status: Status = determineStatus(forAgent, now);
    return {
      name,
      display,
      role,
      status,
      lastEvent,
      lastTask,
      eventsLast24h: recent.length,
    };
  });
}

function determineStatus(forAgent: AgentEvent[], nowMs: number): Status {
  const last = forAgent[0];
  if (!last) return "idle";
  const ageMs = nowMs - new Date(last.created_at).getTime();
  if (
    last.event_type === "tool_call" ||
    last.event_type === "scheduled_job_started" ||
    last.event_type === "launch_step_started"
  ) {
    if (ageMs < 5 * 60 * 1000) return "busy";
  }
  if (ageMs < 24 * 60 * 60 * 1000) return "active";
  return "idle";
}

function summarize(ev: AgentEvent): string {
  const p = ev.payload ?? {};
  switch (ev.event_type) {
    case "tool_call":
      return `Called ${String(p.name ?? "tool")}`;
    case "tool_result":
      return `${String(p.name ?? "tool")} → ${p.is_error ? "error" : "ok"}`;
    case "message.agent":
      return typeof p.text === "string" ? p.text.slice(0, 180) : "Spoke to the user.";
    case "specialist_completed":
      return `Completed: ${String(p.summary_preview ?? p.task ?? "task")}`;
    case "launch_step_started":
      return `Starting ${String(p.step ?? "step")}`;
    case "launch_step_completed":
      return `Completed ${String(p.step ?? "step")}`;
    case "scheduled_job_started":
      return `Running ${String(p.job ?? "job")}`;
    case "scheduled_job_completed":
      return `${String(p.job ?? "job")} complete`;
    case "approval_requested":
      return `Requested: ${String(p.summary ?? "")}`;
    case "spend_authorized":
      return `Authorized $${Math.round(Number(p.amount_cents ?? 0) / 100)} at ${String(p.merchant_name ?? "merchant")}`;
    default:
      return ev.event_type;
  }
}
