"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { TopUpSheet } from "@/components/credits/TopUpSheet";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import {
  type BillingState,
  type CreditBalanceState,
  type CreditTransaction,
  getBilling,
  getCreditBalance,
  listCreditTransactions,
  openBillingPortal,
  startBillingCheckout,
} from "@/lib/api";

const UPGRADE_TIERS: { target: "operator" | "portfolio"; label: string }[] = [
  { target: "operator", label: "Upgrade to Operator" },
  { target: "portfolio", label: "Upgrade to Portfolio" },
];

export default function BillingPage() {
  return (
    <Suspense fallback={null}>
      <BillingContent />
    </Suspense>
  );
}

function BillingContent() {
  const params = useSearchParams();
  const tierResult = params.get("status"); // subscription checkout
  const topUp = params.get("topup"); // credits checkout

  const [tier, setTier] = useState<BillingState | null>(null);
  const [credits, setCredits] = useState<CreditBalanceState | null>(null);
  const [history, setHistory] = useState<CreditTransaction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyTier, setBusyTier] = useState<string | null>(null);
  const [topUpOpen, setTopUpOpen] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [t, c, h] = await Promise.all([
        getBilling().catch(() => null),
        getCreditBalance(),
        listCreditTransactions({ limit: 50 }),
      ]);
      setTier(t);
      setCredits(c);
      setHistory(h);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Stripe returns the user here after checkout — refetch so the new
  // balance shows up without a manual refresh (webhook may need a
  // second to fire; poll a few times).
  useEffect(() => {
    if (topUp !== "success") return;
    let attempts = 0;
    const iv = setInterval(async () => {
      attempts += 1;
      await load();
      if (attempts >= 4) clearInterval(iv);
    }, 1500);
    return () => clearInterval(iv);
  }, [topUp, load]);

  async function goToCheckout(target: "operator" | "portfolio") {
    setBusyTier(target);
    setError(null);
    try {
      const { url } = await startBillingCheckout(target);
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusyTier(null);
    }
  }

  async function goToPortal() {
    setBusyTier("portal");
    setError(null);
    try {
      const { url } = await openBillingPortal();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusyTier(null);
    }
  }

  return (
    <AppShell breadcrumbs={["Helm", "Billing"]}>
      <div className="px-10 pt-8 pb-20 max-w-4xl space-y-6">
        {tierResult === "success" ? (
          <div className="rounded-md border border-sage/50 bg-sage-soft/50 px-4 py-3 text-sm text-sage-2">
            <strong className="font-semibold">Subscription updated.</strong> Stripe confirmed
            the change — your tier reflects the new plan the moment the webhook lands.
          </div>
        ) : null}
        {tierResult === "cancel" ? (
          <div className="rounded-md border border-rule bg-paper-2 px-4 py-3 text-sm text-ink-3">
            Subscription checkout cancelled. Your plan is unchanged.
          </div>
        ) : null}
        {topUp === "success" ? (
          <div className="rounded-md border border-sage/50 bg-sage-soft/50 px-4 py-3 text-sm text-sage-2">
            <strong className="font-semibold">Top-up received.</strong> Your credits will
            appear here within a few seconds.
          </div>
        ) : null}
        {topUp === "cancel" ? (
          <div className="rounded-md border border-rule bg-paper-2 px-4 py-3 text-sm text-ink-3">
            Top-up cancelled. No charge was made.
          </div>
        ) : null}
        {error ? <p className="text-sm text-rose-2">{error}</p> : null}

        <header>
          <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">
            Billing
          </div>
          <h1 className="font-serif text-[44px] leading-none tracking-tightest">
            Credits &amp; plan
          </h1>
        </header>

        {credits && (
          <Card className="border-terracotta/30 bg-terracotta-soft/20">
            <CardHeader>
              <CardTitle>Credits balance</CardTitle>
              <CardDescription>
                One balance for every billable action in Helm — LLM calls, renders, voice,
                publishing, domains. Top up any time, unused credits roll over.
              </CardDescription>
            </CardHeader>
            <div className="flex items-baseline gap-3">
              <span className="font-serif text-[56px] leading-none tabular tracking-tightest">
                ${(credits.balance_cents / 100).toFixed(2)}
              </span>
              <span className="text-[12px] text-ink-3 uppercase tracking-[0.06em]">
                available
              </span>
            </div>
            <div className="flex flex-wrap gap-4 mt-4 text-[12px] text-ink-3">
              <span>
                Lifetime granted:{" "}
                <span className="font-mono tabular text-ink-2">
                  ${(credits.lifetime_granted_cents / 100).toFixed(2)}
                </span>
              </span>
              <span>
                Lifetime purchased:{" "}
                <span className="font-mono tabular text-ink-2">
                  ${(credits.lifetime_purchased_cents / 100).toFixed(2)}
                </span>
              </span>
              <span>
                Lifetime spent:{" "}
                <span className="font-mono tabular text-ink-2">
                  ${(credits.lifetime_spent_cents / 100).toFixed(2)}
                </span>
              </span>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button variant="accent" onClick={() => setTopUpOpen(true)}>
                <Icon name="plus" size={13} /> Top up credits
              </Button>
              <button
                type="button"
                className="inline-flex items-center justify-center h-9 px-3.5 text-[13px] rounded-sm border border-rule bg-paper hover:bg-sand"
                title="Coming soon — one-click export of all business costs for your accountant"
              >
                <Icon name="receipt" size={13} className="mr-1.5" /> Tax export
              </button>
            </div>
          </Card>
        )}

        {tier && (
          <div className="grid grid-cols-12 gap-5">
            <Card className="col-span-6">
              <CardHeader>
                <CardTitle>
                  Current plan · {tier.display_name}
                </CardTitle>
                <CardDescription>
                  Tiers unlock capacity and priority — not a fixed dollar budget.
                </CardDescription>
              </CardHeader>
              <UsageBar
                used={tier.businesses_used}
                cap={tier.max_businesses}
                unit="businesses"
              />
            </Card>

            <Card className="col-span-6">
              <CardHeader>
                <CardTitle>Change plan</CardTitle>
                <CardDescription>
                  {tier.subscription_status === "active"
                    ? "Change plan, update payment method, pause, or cancel via Stripe."
                    : "Higher tiers unlock more businesses + priority swarm access."}
                </CardDescription>
              </CardHeader>
              <div className="flex flex-wrap gap-2">
                {tier.subscription_status === "active" ? (
                  <Button variant="primary" disabled={busyTier !== null} onClick={goToPortal}>
                    {busyTier === "portal" ? "Opening Stripe…" : "Manage subscription"}
                  </Button>
                ) : null}
                {UPGRADE_TIERS.filter((t) => t.target !== tier.tier).map((t) => (
                  <Button
                    key={t.target}
                    variant="accent"
                    disabled={busyTier !== null}
                    onClick={() => goToCheckout(t.target)}
                  >
                    {busyTier === t.target ? "Opening Stripe…" : t.label}
                  </Button>
                ))}
              </div>
              {tier.subscription_status && tier.subscription_status !== "inactive" ? (
                <div className="text-xs text-ink-3 mt-3">
                  Status: <span className="font-mono">{tier.subscription_status}</span>
                </div>
              ) : null}
            </Card>
          </div>
        )}

        <section>
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-[13px] font-medium text-ink-2 uppercase tracking-[0.08em]">
              Transaction history
            </h2>
            {history && (
              <span className="text-[11px] text-ink-3">
                {history.length} recent
              </span>
            )}
          </div>
          {history === null ? (
            <p className="text-sm text-ink-3">Loading…</p>
          ) : history.length === 0 ? (
            <div className="rounded-md border border-rule bg-paper p-6 text-sm text-ink-3">
              No credit activity yet. Your $5 starter grant should already be showing above.
            </div>
          ) : (
            <div className="rounded-md border border-rule bg-paper">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-rule text-[11px] uppercase tracking-[0.06em] text-ink-3">
                    <th className="text-left font-medium px-4 py-3 w-[150px]">When</th>
                    <th className="text-left font-medium px-4 py-3 w-[130px]">Kind</th>
                    <th className="text-left font-medium px-4 py-3">Description</th>
                    <th className="text-right font-medium px-4 py-3 w-[110px]">Amount</th>
                    <th className="text-right font-medium px-4 py-3 w-[110px]">Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((t) => (
                    <TransactionRow key={t.id} txn={t} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <TopUpSheet
        open={topUpOpen}
        onClose={() => setTopUpOpen(false)}
        minTopUpCents={credits?.min_top_up_cents ?? 2000}
        onSuccess={() => {
          void load();
        }}
      />
    </AppShell>
  );
}

function TransactionRow({ txn }: { txn: CreditTransaction }) {
  const positive = txn.amount_cents > 0;
  const sign = positive ? "+" : "−";
  const abs = Math.abs(txn.amount_cents) / 100;
  return (
    <tr className="border-b border-rule last:border-b-0 hover:bg-sand/60">
      <td className="px-4 py-3 text-[12px] text-ink-3 font-mono align-top">
        {new Date(txn.created_at).toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </td>
      <td className="px-4 py-3 text-[12px] align-top">
        <span className={cn("chip", chipTone(txn.kind))}>{kindLabel(txn.kind)}</span>
      </td>
      <td className="px-4 py-3 text-[13px] text-ink-2 align-top">
        <div className="line-clamp-2">{txn.description}</div>
      </td>
      <td className="px-4 py-3 text-right text-[13px] font-mono tabular align-top">
        <span className={positive ? "text-sage-2" : "text-ink-2"}>
          {sign}${abs.toFixed(2)}
        </span>
      </td>
      <td className="px-4 py-3 text-right text-[12px] font-mono tabular text-ink-3 align-top">
        ${(txn.balance_after_cents / 100).toFixed(2)}
      </td>
    </tr>
  );
}

function kindLabel(k: CreditTransaction["kind"]): string {
  switch (k) {
    case "starter_grant":
      return "welcome";
    case "subscription_grant":
      return "plan usage";
    case "purchase":
      return "top-up";
    case "reserve":
      return "hold";
    case "commit":
      return "used";
    case "refund":
      return "refund";
    case "adjustment":
      return "adjustment";
  }
}

function chipTone(k: CreditTransaction["kind"]): string {
  if (k === "purchase" || k === "starter_grant" || k === "subscription_grant")
    return "chip-sage";
  if (k === "commit") return "chip-terra";
  if (k === "refund") return "chip-amber";
  if (k === "reserve") return "";
  return "";
}

function UsageBar({ used, cap, unit }: { used: number; cap: number; unit: string }) {
  const unlimited = cap === 0;
  const pct = unlimited ? 0 : Math.min((used / cap) * 100, 100);
  const barColor = pct > 90 ? "bg-rose-2" : pct > 66 ? "bg-amber-2" : "bg-terracotta";
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="font-serif text-[36px] leading-none tabular">{used}</span>
        <span className="text-sm text-ink-3 font-mono">
          {unlimited ? "unlimited" : `of ${cap} ${unit}`}
        </span>
      </div>
      {!unlimited ? (
        <div className="h-1.5 w-full bg-sand rounded-full overflow-hidden">
          <div className={cn("h-full transition-all", barColor)} style={{ width: `${pct}%` }} />
        </div>
      ) : null}
    </div>
  );
}
