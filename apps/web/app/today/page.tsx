"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Sparkline, FlowStream, Donut } from "@/components/design/Charts";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import {
  type BusinessToday,
  getToday,
  listApprovals,
  type Approval,
  type TodaySummary,
} from "@/lib/api";

// Helm's real specialist lineup (docs/AGENTS.md). Used so the Swarm card
// reflects the product, not marketing fluff — the statuses are illustrative
// until we wire up live agent-session status to the API.
const SPECIALISTS: { name: string; role: string; status: "active" | "busy" | "idle" }[] = [
  { name: "Atlas", role: "CEO · Orchestrator", status: "active" },
  { name: "Idea Scout", role: "Concepts & research", status: "active" },
  { name: "Product Builder", role: "Storefronts & SKUs", status: "busy" },
  { name: "Creative Director", role: "Brand & assets", status: "active" },
  { name: "Ads Operator", role: "Paid media", status: "active" },
  { name: "Growth Analyst", role: "Experiments", status: "idle" },
];

export default function TodayPage() {
  const [data, setData] = useState<TodaySummary | null>(null);
  const [pending, setPending] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    function refresh() {
      getToday()
        .then((d) => {
          if (!cancelled) setData(d);
        })
        .catch((e) => {
          if (!cancelled) setError(e instanceof Error ? e.message : String(e));
        });
      listApprovals("pending")
        .then((rows) => {
          if (!cancelled) setPending(rows.slice(0, 3));
        })
        .catch(() => {
          // Non-fatal — briefing card is optional decoration.
        });
    }
    refresh();
    const interval = setInterval(refresh, 60_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return (
    <AppShell breadcrumbs={["Helm", "Today"]}>
      <div className="px-10 pt-8 pb-20">
        {error ? <p className="text-sm text-rose-2">{error}</p> : null}
        {!data && !error ? <p className="text-sm text-ink-3">Loading…</p> : null}

        {data && data.businesses.length === 0 ? <ZeroBusinessHero /> : null}

        {data && data.businesses.length > 0 ? (
          <>
            <PageHead />

            <div className="grid grid-cols-12 gap-5">
              <MoneyCard
                label="Money in"
                chip="today"
                chipTone="sage"
                valueCents={data.revenue_today_cents}
                color="oklch(0.58 0.07 145)"
                data={[22, 28, 31, 26, 34, 38, 42, 40, 46, 48]}
              />
              <MoneyCard
                label="Money out"
                chip="today"
                chipTone="terra"
                valueCents={data.spend_today_cents}
                color="var(--terracotta)"
                data={[24, 25, 27, 26, 28, 29, 30, 31, 31, 32]}
              />
              <NetCard netCents={data.net_today_cents} />

              <FlowCard />
              <BriefingCard pending={pending} />

              <SwarmCard />
              <BusinessesCard businesses={data.businesses} />
            </div>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function PageHead() {
  const d = new Date();
  const datestr = d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  const hour = d.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  return (
    <div className="flex items-end justify-between mb-7">
      <div>
        <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">{datestr}</div>
        <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
          {greeting}.
        </h1>
        <div className="text-sm text-ink-3">
          Atlas is on the bridge. Here&apos;s where your holdings stand.
        </div>
      </div>
      <div className="flex gap-2">
        <Link
          href="/approvals"
          className="inline-flex items-center gap-1.5 px-3.5 h-9 text-[13px] rounded-sm border border-rule bg-paper hover:bg-sand text-ink"
        >
          <Icon name="check" size={13} /> Approvals
        </Link>
        <Link
          href="/chat"
          className="inline-flex items-center gap-1.5 px-3.5 h-9 text-[13px] rounded-sm bg-ink border border-ink text-paper hover:bg-terracotta hover:border-terracotta"
        >
          <Icon name="sparkle" size={13} /> Brief Atlas
        </Link>
      </div>
    </div>
  );
}

function MoneyCard({
  label,
  chip,
  chipTone,
  valueCents,
  color,
  data,
}: {
  label: string;
  chip: string;
  chipTone: "sage" | "terra";
  valueCents: number;
  color: string;
  data: number[];
}) {
  return (
    <div className="col-span-4 rounded-md border border-rule bg-paper p-[22px]">
      <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
        {label}
        <span className={cn("chip", chipTone === "sage" ? "chip-sage" : "chip-terra")}>{chip}</span>
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="font-serif text-[40px] leading-none tracking-tightest tabular">
          ${(valueCents / 100).toFixed(0)}
          <span className="text-[20px] text-ink-3 ml-1">
            .{(valueCents % 100).toString().padStart(2, "0")}
          </span>
        </div>
        <div className="text-xs text-ink-3 tabular">across every business, last 24h</div>
      </div>
      <div className="mt-3">
        <Sparkline data={data} color={color} fill />
      </div>
    </div>
  );
}

function NetCard({ netCents }: { netCents: number }) {
  const positive = netCents >= 0;
  return (
    <div className="col-span-4 rounded-md border border-rule bg-paper p-[22px]">
      <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
        Net today
        <span className={cn("chip", positive ? "chip-sage" : "chip-rose")}>
          {positive ? "Up" : "Down"}
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        <div
          className={cn(
            "font-serif text-[40px] leading-none tracking-tightest tabular",
            positive ? "text-sage-2" : "text-rose-2",
          )}
        >
          {positive ? "+" : "−"}${(Math.abs(netCents) / 100).toFixed(0)}
        </div>
        <div className="text-xs text-ink-3 tabular">revenue minus spend, 24h</div>
      </div>
      <div className="mt-3">
        <Sparkline
          data={[8.1, 8.5, 8.9, 9.2, 9.6, 10.1, 10.4, 10.7, 11.0, 11.2]}
          color="var(--ink)"
          fill
        />
      </div>
    </div>
  );
}

function FlowCard() {
  return (
    <div className="col-span-8 rounded-md border border-rule bg-paper p-[22px]">
      <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
        Cash flow — last 12 weeks
        <div className="inline-flex gap-0.5 p-[3px] bg-sand rounded-[8px]">
          {(["Weekly", "Monthly"] as const).map((t, i) => (
            <button
              key={t}
              type="button"
              className={cn(
                "px-3 py-1.5 text-[12.5px] rounded-[6px]",
                i === 0 ? "bg-paper text-ink shadow-sm" : "text-ink-3",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <FlowStream />
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
  );
}

function BriefingCard({ pending }: { pending: Approval[] }) {
  return (
    <div className="col-span-4 rounded-md border border-rule bg-paper p-[22px]">
      <div className="text-[13px] font-medium text-ink-2 mb-3.5">Atlas&apos; briefing</div>
      <div className="font-serif text-[20px] leading-snug tracking-[-0.01em] text-ink mb-4">
        {pending.length === 0
          ? "Nothing's waiting on you. The swarm is executing."
          : `${pending.length} thing${pending.length === 1 ? "" : "s"} need${pending.length === 1 ? "s" : ""} your eyes today.`}
      </div>
      <div className="flex flex-col gap-3">
        {pending.length === 0 ? (
          <BriefItem
            num="—"
            title="Check in with Atlas"
            desc="Open the chat and ask what's worth doing next."
            href="/chat"
          />
        ) : (
          pending.map((a, i) => (
            <BriefItem
              key={a.id}
              num={String(i + 1).padStart(2, "0")}
              title={briefTitle(a)}
              desc={briefDesc(a)}
              href={`/approvals/${a.id}`}
            />
          ))
        )}
      </div>
    </div>
  );
}

function briefTitle(a: Approval): string {
  if (a.kind === "spend" && typeof a.details?.amount_cents === "number") {
    const amt = Math.round((a.details.amount_cents as number) / 100);
    const merchant =
      typeof a.details?.merchant_hint === "string" ? (a.details.merchant_hint as string) : "a vendor";
    return `Approve $${amt} to ${merchant}`;
  }
  return a.summary.length > 56 ? a.summary.slice(0, 53) + "…" : a.summary;
}

function briefDesc(a: Approval): string {
  const when = new Date(a.expires_at).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
  return `Expires ${when} — tap to review`;
}

function BriefItem({
  num,
  title,
  desc,
  href,
}: {
  num: string;
  title: string;
  desc: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="flex gap-3 p-3 bg-paper-2 rounded-sm border border-rule hover:bg-sand transition-colors"
    >
      <div className="font-serif text-[18px] text-terracotta leading-none">{num}</div>
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-medium truncate">{title}</div>
        <div className="text-xs text-ink-3 mt-0.5">{desc}</div>
      </div>
    </Link>
  );
}

function SwarmCard() {
  return (
    <div className="col-span-6 rounded-md border border-rule bg-paper p-[22px]">
      <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
        Specialist swarm
        <span className="chip chip-sage">8 ready</span>
      </div>
      <div className="flex flex-col gap-2">
        {SPECIALISTS.map((a) => (
          <div
            key={a.name}
            className="flex items-center gap-2.5 px-3 py-2.5 bg-paper rounded-sm border border-rule"
          >
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                a.status === "active"
                  ? "bg-sage shadow-[0_0_0_4px_var(--sage-soft)]"
                  : a.status === "busy"
                    ? "bg-amber shadow-[0_0_0_4px_var(--amber-soft)]"
                    : "bg-sand-2 shadow-[0_0_0_4px_var(--sand)]",
              )}
            />
            <div className="flex-1 min-w-0">
              <span className="text-[13px] font-medium">{a.name}</span>
              <span className="text-[12px] text-ink-3 ml-2">{a.role}</span>
            </div>
            <div className="text-[11px] text-ink-3 capitalize">{a.status}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BusinessesCard({ businesses }: { businesses: BusinessToday[] }) {
  const total = businesses.reduce((sum, b) => sum + Math.abs(b.revenue_today_cents), 0) || 1;
  const DONUT_COLORS = ["var(--ink)", "var(--terracotta)", "var(--sage)", "var(--amber)"] as const;
  const ROW_COLORS = [
    "var(--ink)",
    "var(--terracotta)",
    "var(--sage)",
    "var(--amber)",
    "var(--ink-3)",
  ] as const;
  const segments = businesses.slice(0, 4).map((b, i) => ({
    value: Math.max(b.revenue_today_cents, 1),
    color: DONUT_COLORS[i] ?? "var(--ink-3)",
  }));
  return (
    <div className="col-span-6 rounded-md border border-rule bg-paper p-[22px]">
      <div className="flex items-center justify-between mb-3.5 text-[13px] font-medium text-ink-2">
        Businesses
        <Link href="/businesses" className="text-[12px] text-terracotta-2 hover:underline">
          All businesses →
        </Link>
      </div>
      <div className="flex items-center gap-5">
        <Donut segments={segments} size={140} />
        <div className="flex-1 flex flex-col gap-2.5">
          {businesses.slice(0, 5).map((b, i) => (
            <Link
              key={b.id}
              href={`/businesses/${b.id}`}
              className="flex items-center gap-2.5 text-[13px] hover:text-terracotta-2 transition-colors"
            >
              <div
                className="h-2.5 w-2.5 rounded-[3px] shrink-0"
                style={{ background: ROW_COLORS[i] ?? "var(--ink-3)" }}
              />
              <div className="flex-1 min-w-0 truncate">{b.name}</div>
              <div className="font-mono text-xs">
                ${(b.revenue_today_cents / 100).toFixed(0)}
              </div>
              <div className="text-[11px] text-ink-3 w-10 text-right">
                {Math.round((b.revenue_today_cents / total) * 100)}%
              </div>
            </Link>
          ))}
          {businesses.length === 0 && (
            <div className="text-xs text-ink-3">
              No revenue yet today. Ask Atlas to spin up a new venture.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ZeroBusinessHero() {
  return (
    <div className="max-w-2xl mx-auto text-center py-16 space-y-5">
      <div className="text-xs font-medium tracking-[0.08em] text-terracotta uppercase">
        Welcome to Helm
      </div>
      <h1 className="font-serif text-[44px] leading-[1.1] tracking-tightest">
        Tell your CEO Agent what to launch.
      </h1>
      <p className="text-sm text-ink-3 max-w-md mx-auto leading-relaxed">
        Eight specialists are standing by. Idea Scout finds proven concepts. Creative Director
        builds the brand. Product Builder stands up the storefront. Ads Operator buys the first
        traffic.
      </p>
      <div className="flex justify-center gap-2 pt-2">
        <Link
          href="/onboarding"
          className="inline-flex items-center justify-center h-11 px-5 rounded-sm bg-terracotta text-paper text-sm font-medium border border-terracotta hover:bg-terracotta-2"
        >
          <Icon name="sparkle" size={13} /> Start your first venture
        </Link>
        <Link
          href="/chat"
          className="inline-flex items-center justify-center h-11 px-5 rounded-sm border border-rule bg-paper text-sm text-ink hover:bg-sand"
        >
          Or just talk to Atlas
        </Link>
      </div>
      <div className="text-xs text-ink-3 mt-6">Or choose a starting point</div>
      <div className="flex flex-wrap justify-center gap-2">
        {["E-commerce brand", "SaaS product", "Local service", "Digital course", "Newsletter"].map(
          (p) => (
            <span
              key={p}
              className="text-xs px-3 py-1.5 bg-sand rounded-full text-ink-2 whitespace-nowrap"
            >
              {p}
            </span>
          ),
        )}
      </div>
    </div>
  );
}
