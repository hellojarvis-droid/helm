"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import { type AgentEvent, type Business, listAllEvents, listBusinesses } from "@/lib/api";

const EVENT_TYPES = [
  "message.user",
  "message.agent",
  "tool_call",
  "tool_result",
  "specialist_completed",
  "approval_requested",
  "approval_approved",
  "approval_denied",
  "approval_modified",
  "spend_authorized",
  "spend_declined",
  "revenue_received",
  "launch_started",
  "launch_step_started",
  "launch_step_completed",
  "launch_step_failed",
  "launch_step_skipped",
  "launch_completed",
  "launch_failed",
  "scheduled_job_started",
  "scheduled_job_completed",
  "sync_push_ok",
  "sync_push_failed",
  "sync_pull_ok",
  "sync_pull_failed",
  "sync_pull_conflict",
  "render_job_queued",
  "render_job_running",
  "render_job_completed",
  "render_job_failed",
  "kill_switch_activated",
];

export default function EventsPage() {
  return (
    <Suspense fallback={null}>
      <EventsContent />
    </Suspense>
  );
}

function EventsContent() {
  const params = useSearchParams();
  const initialBiz = params.get("business_id") ?? "";
  const initialAgent = params.get("agent_name") ?? "";
  const initialType = params.get("event_type") ?? "";

  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [biz, setBiz] = useState<string>(initialBiz);
  const [agent, setAgent] = useState<string>(initialAgent);
  const [eventType, setEventType] = useState<string>(initialType);
  const [rows, setRows] = useState<AgentEvent[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [reachedEnd, setReachedEnd] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listBusinesses()
      .then(setBusinesses)
      .catch(() => {
        /* non-fatal; business filter is optional */
      });
  }, []);

  const filters = useMemo(
    () => ({
      businessId: biz || undefined,
      agentName: agent || undefined,
      eventType: eventType || undefined,
    }),
    [biz, agent, eventType],
  );

  const load = useCallback(
    async (beforeId?: number) => {
      setLoading(true);
      setError(null);
      try {
        const fresh = await listAllEvents({ ...filters, beforeId, limit: 50 });
        if (fresh.length < 50) setReachedEnd(true);
        setRows((prev) => (beforeId && prev ? [...prev, ...fresh] : fresh));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [filters],
  );

  useEffect(() => {
    setRows(null);
    setReachedEnd(false);
    void load();
  }, [load]);

  const oldestId = rows?.[rows.length - 1]?.id;

  return (
    <AppShell breadcrumbs={["Helm", "Events"]}>
      <div className="px-10 pt-8 pb-20 max-w-5xl">
        <header className="mb-7">
          <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
            Events
          </h1>
          <p className="text-sm text-ink-3 max-w-prose">
            The event-sourced log of every agent action across your portfolio. Filterable — this
            is the record you can replay.
          </p>
        </header>

        <div className="flex flex-wrap gap-3 mb-5">
          <select
            value={biz}
            onChange={(e) => setBiz(e.target.value)}
            className="h-9 rounded-sm border border-rule bg-paper px-3 text-[13px] text-ink"
          >
            <option value="">All businesses</option>
            {businesses.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
          <select
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
            className="h-9 rounded-sm border border-rule bg-paper px-3 text-[13px] text-ink"
          >
            <option value="">All agents</option>
            <option value="ceo_agent">Atlas</option>
            <option value="creative_director">Creative Director</option>
            <option value="product_builder">Product Builder</option>
            <option value="ads_operator">Ads Operator</option>
            <option value="growth_analyst">Growth Analyst</option>
            <option value="social_engagement">Social Engagement</option>
            <option value="customer_service">Customer Service</option>
            <option value="finance_ops">Finance Ops</option>
            <option value="idea_scout">Idea Scout</option>
            <option value="launch_workflow">Launch workflow</option>
            <option value="stripe_authorization">Stripe authorization</option>
            <option value="sync_bus">Sync bus</option>
            <option value="muse">Creative Studio (Muse)</option>
          </select>
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="h-9 rounded-sm border border-rule bg-paper px-3 text-[13px] text-ink"
          >
            <option value="">All event types</option>
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          {(biz || agent || eventType) && (
            <button
              type="button"
              onClick={() => {
                setBiz("");
                setAgent("");
                setEventType("");
              }}
              className="h-9 px-3 rounded-sm text-[13px] text-ink-3 hover:text-ink hover:bg-sand"
            >
              Clear
            </button>
          )}
        </div>

        {error && (
          <div className="mb-4 text-sm text-rose-2">{error}</div>
        )}

        {rows === null ? (
          <p className="text-sm text-ink-3">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="rounded-md border border-rule bg-paper p-8 max-w-xl">
            <div className="font-serif text-[22px] leading-tight mb-2">No events match.</div>
            <p className="text-sm text-ink-3">
              Try clearing filters or widen the date range via the pagination below.
            </p>
          </div>
        ) : (
          <div className="rounded-md border border-rule bg-paper">
            <table className="w-full">
              <thead>
                <tr className="border-b border-rule text-[11px] uppercase tracking-[0.06em] text-ink-3">
                  <th className="text-left font-medium px-4 py-3 w-[140px]">When</th>
                  <th className="text-left font-medium px-4 py-3 w-[160px]">Agent</th>
                  <th className="text-left font-medium px-4 py-3 w-[200px]">Type</th>
                  <th className="text-left font-medium px-4 py-3">Summary</th>
                  <th className="text-right font-medium px-4 py-3 w-[80px]">Cost</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <EventRow key={r.id} row={r} businesses={businesses} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {rows && rows.length > 0 && !reachedEnd && (
          <button
            type="button"
            onClick={() => oldestId && void load(oldestId)}
            disabled={loading}
            className="mt-4 text-sm text-ink-3 hover:text-ink disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load older"}
          </button>
        )}
        {rows && rows.length > 0 && reachedEnd && (
          <p className="mt-4 text-xs text-ink-3">— end of log —</p>
        )}
      </div>
    </AppShell>
  );
}

function EventRow({ row, businesses }: { row: AgentEvent; businesses: Business[] }) {
  const biz = businesses.find((b) => b.id === row.business_id);
  return (
    <tr className="border-b border-rule last:border-b-0 hover:bg-sand/60">
      <td className="px-4 py-3 text-[12px] text-ink-3 font-mono align-top">
        {new Date(row.created_at).toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </td>
      <td className="px-4 py-3 text-[12px] align-top">
        <div className="text-ink font-medium">{prettyAgent(row.agent_name)}</div>
        {biz && (
          <Link
            href={`/businesses/${biz.id}`}
            className="text-[11px] text-ink-3 hover:text-ink"
          >
            {biz.name}
          </Link>
        )}
      </td>
      <td className="px-4 py-3 text-[12px] align-top">
        <span className={cn("chip", chipTone(row.event_type))}>{row.event_type}</span>
      </td>
      <td className="px-4 py-3 text-[13px] text-ink-2 align-top max-w-[540px]">
        <div className="truncate">{summarize(row)}</div>
      </td>
      <td className="px-4 py-3 text-right text-[12px] font-mono align-top">
        {row.cost_cents === 0
          ? ""
          : row.cost_cents < 100
            ? `${row.cost_cents}¢`
            : `$${(row.cost_cents / 100).toFixed(2)}`}
      </td>
    </tr>
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
    stripe_authorization: "Stripe auth",
    user: "You",
    runtime: "Runtime",
  };
  return MAP[name] ?? name;
}

function chipTone(eventType: string): string {
  if (eventType.startsWith("approval_")) return "chip-terra";
  if (eventType === "spend_authorized" || eventType === "revenue_received") return "chip-sage";
  if (eventType === "sync_pull_conflict") return "chip-amber";
  if (eventType.startsWith("sync_") && eventType.endsWith("_ok")) return "chip-sage";
  if (eventType === "spend_declined" || eventType.endsWith("_failed") || eventType === "kill_switch_activated") return "chip-rose";
  if (eventType.startsWith("launch_") || eventType.startsWith("scheduled_job_")) return "chip-amber";
  if (eventType.startsWith("render_job_") && eventType.endsWith("_completed")) return "chip-sage";
  if (eventType.startsWith("render_job_")) return "chip-amber";
  return "";
}

function summarize(ev: AgentEvent): string {
  const p = ev.payload ?? {};
  switch (ev.event_type) {
    case "message.user":
      return typeof p.text === "string" ? p.text : "user message";
    case "message.agent":
      return typeof p.text === "string" ? p.text : "agent response";
    case "tool_call":
      return `Called ${String(p.name ?? "tool")}`;
    case "tool_result":
      return `${String(p.name ?? "tool")} → ${p.is_error ? "error" : "ok"}`;
    case "approval_requested":
      return `Requested: ${String(p.summary ?? p.kind ?? "approval")}`;
    case "approval_approved":
    case "approval_denied":
      return `${String(p.kind ?? "approval")} ${ev.event_type.split("_")[1]}`;
    case "spend_authorized":
      return `Authorized $${Math.round(Number(p.amount_cents ?? 0) / 100)} at ${String(p.merchant_name ?? p.merchant_category ?? "merchant")}`;
    case "spend_declined":
      return `Declined: ${String(p.reason ?? "policy")}`;
    case "revenue_received":
      return `Revenue: $${Math.round(Number(p.amount_cents ?? 0) / 100)}`;
    case "launch_step_started":
      return `Starting ${String(p.step ?? "step")}`;
    case "launch_step_completed":
      return `Completed ${String(p.step ?? "step")}`;
    case "launch_step_failed":
      return `${String(p.step ?? "step")} failed: ${String(p.error ?? "")}`;
    case "launch_step_skipped":
      return `Skipped ${String(p.step ?? "step")}`;
    case "scheduled_job_started":
      return `Scheduled: ${String(p.job ?? "job")}`;
    case "scheduled_job_completed":
      return `${String(p.job ?? "job")} done`;
    case "specialist_completed":
      return `${String(p.summary_preview ?? "completed")}`;
    case "sync_push_ok":
      return `Pushed ${String(p.entity_type ?? "entity")} to the provider`;
    case "sync_push_failed":
      return `Push failed for ${String(p.entity_type ?? "entity")}: ${String((p.detail as Record<string, unknown> | undefined)?.error ?? "")}`;
    case "sync_pull_ok":
      return `Pulled ${String(p.entity_type ?? "entity")} from the provider`;
    case "sync_pull_failed":
      return `Pull failed for ${String(p.entity_type ?? "entity")}: ${String((p.detail as Record<string, unknown> | undefined)?.error ?? "")}`;
    case "sync_pull_conflict":
      return `Conflict on ${String(p.entity_type ?? "entity")} — external change ignored (Helm wins)`;
    case "render_job_queued":
    case "render_job_running":
      return `Queued render on ${String(p.provider ?? "provider")} — ${String(p.mode ?? "")}`;
    case "render_job_completed":
      return `Render completed on ${String(p.provider ?? "provider")}`;
    case "render_job_failed":
      return `Render failed on ${String(p.provider ?? "provider")}: ${String(p.error ?? "")}`;
    default:
      return JSON.stringify(p).slice(0, 200);
  }
}
