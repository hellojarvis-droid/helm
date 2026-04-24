"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Donut, FlowStream, Sparkline } from "@/components/design/Charts";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import {
  type AgentEvent,
  type Business,
  type TodaySummary,
  getToday,
  listAllEvents,
  listBusinesses,
} from "@/lib/api";

interface BusinessMoney {
  business: Business;
  revenueCents: number;
  spendCents: number;
  llmCents: number;
}

interface MoneyData {
  today: TodaySummary;
  businesses: Business[];
  spend: AgentEvent[];
  revenue: AgentEvent[];
  llm: AgentEvent[];
  declines: AgentEvent[];
}

const WINDOWS: { key: "7d" | "30d" | "90d"; label: string; days: number }[] = [
  { key: "7d", label: "7 days", days: 7 },
  { key: "30d", label: "30 days", days: 30 },
  { key: "90d", label: "90 days", days: 90 },
];

export default function MoneyPage() {
  const [windowKey, setWindowKey] = useState<"7d" | "30d" | "90d">("30d");
  const [data, setData] = useState<MoneyData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [today, businesses, spend, revenue, llm, declines] = await Promise.all([
          getToday(),
          listBusinesses(),
          listAllEvents({ eventType: "spend_authorized", limit: 200 }),
          listAllEvents({ eventType: "revenue_received", limit: 200 }),
          listAllEvents({ eventType: "message.agent", limit: 200 }),
          listAllEvents({ eventType: "spend_declined", limit: 100 }),
        ]);
        if (!cancelled) {
          setData({ today, businesses, spend, revenue, llm, declines });
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const windowSpec = WINDOWS.find((w) => w.key === windowKey)!;

  const rollup = data
    ? rollupData(data, windowSpec.days)
    : null;

  return (
    <AppShell breadcrumbs={["Helm", "Money"]}>
      <div className="px-10 pt-8 pb-20 max-w-5xl">
        <header className="mb-7 flex items-end justify-between">
          <div>
            <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
              Money
            </h1>
            <p className="text-sm text-ink-3 max-w-prose">
              Revenue, spend, agent cost — across every business. Everything reconciles to the
              event log: tap any number to drill in.
            </p>
          </div>
          <div className="inline-flex gap-0.5 p-[3px] bg-sand rounded-[8px]">
            {WINDOWS.map((w) => (
              <button
                key={w.key}
                type="button"
                onClick={() => setWindowKey(w.key)}
                className={cn(
                  "px-3.5 py-1.5 text-[12.5px] rounded-[6px]",
                  windowKey === w.key
                    ? "bg-paper text-ink shadow-sm"
                    : "text-ink-3 hover:text-ink",
                )}
              >
                {w.label}
              </button>
            ))}
          </div>
        </header>

        {error && (
          <div className="mb-5 rounded-md border border-rose-2/50 bg-rose-soft/50 p-4 text-sm text-rose-2">
            {error}
          </div>
        )}

        {data === null ? (
          <p className="text-sm text-ink-3">Loading…</p>
        ) : rollup === null ? null : (
          <div className="grid grid-cols-12 gap-5">
            <StatCard
              className="col-span-4"
              label={`Revenue · ${windowSpec.label}`}
              value={`$${rollup.revenueDollars}`}
              sub="total payments received across businesses"
              color="oklch(0.58 0.07 145)"
              spark={rollup.revenueSpark}
            />
            <StatCard
              className="col-span-4"
              label={`Spend · ${windowSpec.label}`}
              value={`$${rollup.spendDollars}`}
              sub="Stripe-authorized card spend"
              color="var(--terracotta)"
              spark={rollup.spendSpark}
            />
            <NetCard
              className="col-span-4"
              netCents={rollup.netCents}
              windowLabel={windowSpec.label}
            />

            <div className="col-span-8 rounded-md border border-rule bg-paper p-[22px]">
              <div className="flex items-center justify-between mb-4 text-[13px] font-medium text-ink-2">
                Flow — revenue vs. spend
                <span className="chip">{windowSpec.label}</span>
              </div>
              <FlowStream inflow={rollup.inflowSeries} outflow={rollup.outflowSeries} />
              <div className="flex gap-5 mt-3 text-xs text-ink-2">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-sm bg-sage" />
                  Money in
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-0.5 w-2 bg-terracotta align-middle" />
                  Money out
                </span>
              </div>
            </div>

            <div className="col-span-4 rounded-md border border-rule bg-paper p-[22px]">
              <div className="text-[13px] font-medium text-ink-2 mb-3.5">
                Revenue by business
              </div>
              {rollup.businessRevenue.length === 0 ? (
                <p className="text-xs text-ink-3">
                  No revenue tracked in this window yet. Connect Stripe Connect webhooks and
                  customer payment intents start counting here.
                </p>
              ) : (
                <div className="flex items-center gap-4">
                  <Donut
                    segments={rollup.businessRevenue.slice(0, 4).map((b, i) => ({
                      value: Math.max(b.revenueCents, 1),
                      color: ["var(--ink)", "var(--terracotta)", "var(--sage)", "var(--amber)"][i]!,
                    }))}
                    size={120}
                  />
                  <div className="flex-1 flex flex-col gap-2 text-[12.5px]">
                    {rollup.businessRevenue.slice(0, 5).map((b, i) => (
                      <Link
                        key={b.business.id}
                        href={`/businesses/${b.business.id}`}
                        className="flex items-center gap-2 hover:text-terracotta-2"
                      >
                        <span
                          className="h-2.5 w-2.5 rounded-[3px]"
                          style={{
                            background: ["var(--ink)", "var(--terracotta)", "var(--sage)", "var(--amber)", "var(--ink-3)"][i] ?? "var(--ink-3)",
                          }}
                        />
                        <span className="flex-1 truncate">{b.business.name}</span>
                        <span className="font-mono">${Math.round(b.revenueCents / 100)}</span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="col-span-6 rounded-md border border-rule bg-paper p-[22px]">
              <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
                Agent compute
                <span className="chip">{windowSpec.label}</span>
              </div>
              <div className="font-serif text-[36px] leading-none tracking-tightest tabular">
                ${rollup.llmDollars}
              </div>
              <p className="text-xs text-ink-3 mt-2">
                What we paid Anthropic to run the swarm this window. Billed back to you as
                metered usage on the Founder / Operator / Portfolio tier.
              </p>
            </div>

            <div className="col-span-6 rounded-md border border-rule bg-paper p-[22px]">
              <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
                Declined spend
                <span className={cn("chip", rollup.declines.length > 0 ? "chip-rose" : "chip-sage")}>
                  {rollup.declines.length} events
                </span>
              </div>
              {rollup.declines.length === 0 ? (
                <p className="text-xs text-ink-3">
                  Nothing declined. Either caps are healthy or the swarm isn&apos;t pushing the
                  limits — worth a look either way.
                </p>
              ) : (
                <ul className="space-y-2 text-[13px] text-ink-2">
                  {rollup.declines.slice(0, 5).map((d) => (
                    <li key={d.id} className="flex items-center gap-2">
                      <Icon name="close" size={12} className="text-rose-2" />
                      <span className="flex-1 truncate">
                        ${Math.round(Number(d.payload?.amount_cents ?? 0) / 100)} —{" "}
                        {String(d.payload?.reason ?? "policy")}
                      </span>
                      <span className="font-mono text-[11px] text-ink-3">
                        {new Date(d.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="col-span-12 rounded-md border border-rule bg-paper p-[22px]">
              <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
                Recent activity
                <Link href="/events" className="text-[12px] text-terracotta-2 hover:underline">
                  All events →
                </Link>
              </div>
              <div className="divide-y divide-rule">
                {rollup.recent.slice(0, 12).map((ev) => (
                  <div
                    key={ev.id}
                    className="grid items-center gap-3 py-2"
                    style={{ gridTemplateColumns: "110px 1fr 100px" }}
                  >
                    <span className="font-mono text-[11px] text-ink-3">
                      {new Date(ev.created_at).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                    <span className="text-[13px] text-ink-2 truncate">
                      {summarizeEvent(ev)}
                    </span>
                    <span className="text-right font-mono text-[12px] text-ink-2">
                      {ev.event_type === "revenue_received"
                        ? `+$${Math.round(Number(ev.payload?.amount_cents ?? 0) / 100)}`
                        : ev.event_type === "spend_authorized"
                          ? `−$${Math.round(Number(ev.payload?.amount_cents ?? 0) / 100)}`
                          : ""}
                    </span>
                  </div>
                ))}
                {rollup.recent.length === 0 && (
                  <p className="text-xs text-ink-3 py-4">
                    Nothing in the window yet. The scheduler will populate it as the swarm works.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function StatCard({
  className,
  label,
  value,
  sub,
  color,
  spark,
}: {
  className: string;
  label: string;
  value: string;
  sub: string;
  color: string;
  spark: number[];
}) {
  return (
    <div className={cn("rounded-md border border-rule bg-paper p-[22px]", className)}>
      <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-2">{label}</div>
      <div className="font-serif text-[40px] leading-none tracking-tightest tabular">{value}</div>
      <div className="text-xs text-ink-3 mt-1.5">{sub}</div>
      <div className="mt-3">
        <Sparkline data={spark.length >= 2 ? spark : [0, 0.1]} color={color} fill />
      </div>
    </div>
  );
}

function NetCard({
  className,
  netCents,
  windowLabel,
}: {
  className: string;
  netCents: number;
  windowLabel: string;
}) {
  const positive = netCents >= 0;
  return (
    <div className={cn("rounded-md border border-rule bg-paper p-[22px]", className)}>
      <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-2">
        Net · {windowLabel}
      </div>
      <div
        className={cn(
          "font-serif text-[40px] leading-none tracking-tightest tabular",
          positive ? "text-sage-2" : "text-rose-2",
        )}
      >
        {positive ? "+" : "−"}${Math.abs(Math.round(netCents / 100))}
      </div>
      <div className="text-xs text-ink-3 mt-1.5">revenue minus authorized spend</div>
      <div className="mt-3 text-[11px] text-ink-3">
        LLM cost is reported separately below; it sits on your subscription, not the business
        P&amp;L.
      </div>
    </div>
  );
}

function rollupData(
  data: MoneyData,
  windowDays: number,
): {
  revenueDollars: number;
  spendDollars: number;
  llmDollars: number;
  netCents: number;
  revenueSpark: number[];
  spendSpark: number[];
  inflowSeries: number[];
  outflowSeries: number[];
  businessRevenue: BusinessMoney[];
  declines: AgentEvent[];
  recent: AgentEvent[];
} {
  const nowMs = Date.now();
  const cutoff = nowMs - windowDays * 24 * 60 * 60 * 1000;

  const spendCents = sumCentsInWindow(data.spend, cutoff, "amount_cents");
  const revenueCents = sumCentsInWindow(data.revenue, cutoff, "amount_cents");
  const llmCents = sumCostCentsInWindow(data.llm, cutoff);

  const buckets = bucketize(data.spend, data.revenue, cutoff, windowDays);

  // Per-business rollup of revenue.
  const byBiz = new Map<string, BusinessMoney>();
  for (const b of data.businesses) {
    byBiz.set(b.id, { business: b, revenueCents: 0, spendCents: 0, llmCents: 0 });
  }
  for (const ev of data.revenue) {
    if (!ev.business_id || new Date(ev.created_at).getTime() < cutoff) continue;
    const entry = byBiz.get(ev.business_id);
    if (entry)
      entry.revenueCents += Math.abs(Number(ev.payload?.amount_cents ?? 0));
  }
  for (const ev of data.spend) {
    if (!ev.business_id || new Date(ev.created_at).getTime() < cutoff) continue;
    const entry = byBiz.get(ev.business_id);
    if (entry) entry.spendCents += Number(ev.payload?.amount_cents ?? 0);
  }
  const businessRevenue = Array.from(byBiz.values())
    .filter((b) => b.revenueCents > 0)
    .sort((a, b) => b.revenueCents - a.revenueCents);

  const declines = data.declines.filter(
    (e) => new Date(e.created_at).getTime() >= cutoff,
  );
  const recent = [...data.spend, ...data.revenue]
    .filter((e) => new Date(e.created_at).getTime() >= cutoff)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  return {
    revenueDollars: Math.round(revenueCents / 100),
    spendDollars: Math.round(spendCents / 100),
    llmDollars: Number((llmCents / 100).toFixed(2)),
    netCents: revenueCents - spendCents,
    revenueSpark: buckets.inflow,
    spendSpark: buckets.outflow,
    inflowSeries: buckets.inflow,
    outflowSeries: buckets.outflow,
    businessRevenue,
    declines,
    recent,
  };
}

function sumCentsInWindow(events: AgentEvent[], cutoff: number, field: string): number {
  return events
    .filter((e) => new Date(e.created_at).getTime() >= cutoff)
    .reduce((acc, e) => acc + Math.abs(Number(e.payload?.[field] ?? 0)), 0);
}

function sumCostCentsInWindow(events: AgentEvent[], cutoff: number): number {
  return events
    .filter((e) => new Date(e.created_at).getTime() >= cutoff)
    .reduce((acc, e) => acc + (e.cost_cents ?? 0), 0);
}

function bucketize(
  spend: AgentEvent[],
  revenue: AgentEvent[],
  cutoff: number,
  windowDays: number,
): { inflow: number[]; outflow: number[] } {
  const buckets = Math.min(Math.max(windowDays, 7), 30);
  const bucketMs = (Date.now() - cutoff) / buckets;
  const inflow = new Array(buckets).fill(0);
  const outflow = new Array(buckets).fill(0);
  for (const ev of revenue) {
    const t = new Date(ev.created_at).getTime();
    if (t < cutoff) continue;
    const idx = Math.min(Math.floor((t - cutoff) / bucketMs), buckets - 1);
    inflow[idx] += Math.abs(Number(ev.payload?.amount_cents ?? 0)) / 100;
  }
  for (const ev of spend) {
    const t = new Date(ev.created_at).getTime();
    if (t < cutoff) continue;
    const idx = Math.min(Math.floor((t - cutoff) / bucketMs), buckets - 1);
    outflow[idx] += Number(ev.payload?.amount_cents ?? 0) / 100;
  }
  // Ensure min length so FlowStream can render the Bezier — when empty, show
  // a flat baseline rather than crashing.
  while (inflow.length < 2) inflow.push(0);
  while (outflow.length < 2) outflow.push(0);
  return { inflow, outflow };
}

function summarizeEvent(ev: AgentEvent): string {
  if (ev.event_type === "revenue_received") {
    return `Revenue: payment received`;
  }
  if (ev.event_type === "spend_authorized") {
    const merchant = String(ev.payload?.merchant_name ?? ev.payload?.merchant_category ?? "merchant");
    return `Spend authorized at ${merchant}`;
  }
  return ev.event_type;
}
