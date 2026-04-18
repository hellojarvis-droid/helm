"use client";

import { useEffect, useState } from "react";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { type BillingState, getBilling } from "@/lib/api";

export default function BillingPage() {
  const [state, setState] = useState<BillingState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBilling()
      .then(setState)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-10 space-y-6">
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
                <CardTitle>Upgrade</CardTitle>
                <CardDescription>
                  Higher tiers unlock more businesses and a larger included token budget. Self-serve
                  upgrade lands in a later session.
                </CardDescription>
              </CardHeader>
              <div className="flex gap-2">
                <Button variant="accent" disabled>
                  Upgrade (coming soon)
                </Button>
                <a
                  href="mailto:support@helm.app?subject=Upgrade%20request"
                  className="inline-flex items-center justify-center h-10 px-4 text-sm rounded-md border border-iron/30 hover:bg-haze dark:hover:bg-ink/20"
                >
                  Contact support
                </a>
              </div>
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
