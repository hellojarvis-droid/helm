"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { type BillingState, getBilling, openBillingPortal, startBillingCheckout } from "@/lib/api";

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
  const checkoutResult = params.get("status"); // 'success' | 'cancel' set by Stripe redirects
  const [state, setState] = useState<BillingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyTier, setBusyTier] = useState<string | null>(null);

  useEffect(() => {
    getBilling()
      .then(setState)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

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
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-10 space-y-6">
        {checkoutResult === "success" ? (
          <div className="rounded-md border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
            <strong className="font-semibold">Upgrade complete.</strong> Stripe confirmed the
            subscription. Your tier reflects the new plan as soon as the webhook lands — usually
            instant.
          </div>
        ) : null}
        {checkoutResult === "cancel" ? (
          <div className="rounded-md border border-iron/30 bg-haze/40 px-4 py-3 text-sm text-iron">
            Checkout cancelled. Your current plan is unchanged.
          </div>
        ) : null}
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        {!state && !error ? <p className="text-sm text-iron">Loading…</p> : null}
        {state ? (
          <>
            <header>
              <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-1">
                Current plan
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">{state.display_name}</h1>
            </header>

            <Card>
              <CardHeader>
                <CardTitle>Businesses</CardTitle>
                <CardDescription>
                  {state.max_businesses === 0
                    ? "Unlimited."
                    : `${state.display_name} tier is capped at ${state.max_businesses}.`}
                </CardDescription>
              </CardHeader>
              <UsageBar used={state.businesses_used} cap={state.max_businesses} unit="businesses" />
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Month-to-date agent cost</CardTitle>
                <CardDescription>
                  LLM inference cost we&apos;ve billed Anthropic for this month. Exact usage-based
                  overage billing lands in a follow-up — this is a proxy for now.
                </CardDescription>
              </CardHeader>
              <div className="text-2xl font-semibold tabular">
                ${(state.month_to_date_cost_cents / 100).toFixed(2)}
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>
                  {state.subscription_status === "active" ? "Subscription" : "Upgrade"}
                </CardTitle>
                <CardDescription>
                  {state.subscription_status === "active"
                    ? "Change plan, update payment method, pause, or cancel via Stripe."
                    : "Higher tiers unlock more businesses and a larger included token budget."}
                </CardDescription>
              </CardHeader>
              <div className="flex flex-wrap gap-2">
                {state.subscription_status === "active" ? (
                  <Button variant="primary" disabled={busyTier !== null} onClick={goToPortal}>
                    {busyTier === "portal" ? "Opening Stripe…" : "Manage subscription"}
                  </Button>
                ) : null}
                {UPGRADE_TIERS.filter((t) => t.target !== state.tier).map((t) => (
                  <Button
                    key={t.target}
                    variant="accent"
                    disabled={busyTier !== null}
                    onClick={() => goToCheckout(t.target)}
                  >
                    {busyTier === t.target ? "Opening Stripe…" : t.label}
                  </Button>
                ))}
                <a
                  href="mailto:support@helm.app?subject=Upgrade%20request"
                  className="inline-flex items-center justify-center h-10 px-4 text-sm rounded-md border border-iron/30 hover:bg-haze dark:hover:bg-ink/20"
                >
                  Contact support
                </a>
              </div>
              {state.subscription_status && state.subscription_status !== "inactive" ? (
                <div className="text-xs text-iron mt-3">
                  Status: <span className="tabular">{state.subscription_status}</span>
                </div>
              ) : null}
            </Card>
          </>
        ) : null}
      </main>
    </div>
  );
}

function UsageBar({ used, cap, unit }: { used: number; cap: number; unit: string }) {
  const unlimited = cap === 0;
  const pct = unlimited ? 0 : Math.min((used / cap) * 100, 100);
  const barColor = pct > 90 ? "bg-danger" : pct > 66 ? "bg-warning" : "bg-accent";
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-2xl font-semibold tabular">{used}</span>
        <span className="text-sm text-iron tabular">
          {unlimited ? "unlimited" : `of ${cap} ${unit}`}
        </span>
      </div>
      {!unlimited ? (
        <div className="h-2 w-full bg-iron/20 rounded-full overflow-hidden">
          <div className={cn("h-full transition-all", barColor)} style={{ width: `${pct}%` }} />
        </div>
      ) : null}
    </div>
  );
}
