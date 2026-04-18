"use client";

import { useEffect, useState } from "react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { getSpend, type SpendSummary } from "@/lib/api";

export function SpendCard({ businessId }: { businessId: string }) {
  const [s, setS] = useState<SpendSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSpend(businessId)
      .then(setS)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [businessId]);

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Spend</CardTitle>
          <CardDescription>Weekly budget + running cost.</CardDescription>
        </CardHeader>
        <p className="text-sm text-danger">{error}</p>
      </Card>
    );
  }

  if (!s) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Spend</CardTitle>
          <CardDescription>Loading…</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const pct = s.weekly_cap_cents === 0 ? 0 : (s.week_to_date_cents / s.weekly_cap_cents) * 100;
  const barColor = pct > 90 ? "bg-danger" : pct > 66 ? "bg-warning" : "bg-accent";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Spend</CardTitle>
        <CardDescription>
          Week-to-date against the weekly cap. Stripe Issuing declines over this.
        </CardDescription>
      </CardHeader>

      <div className="flex items-baseline justify-between mb-2">
        <div>
          <span className="text-2xl font-semibold tabular">{dollars(s.week_to_date_cents)}</span>
          <span className="text-sm text-iron ml-2">of {dollars(s.weekly_cap_cents)} cap</span>
        </div>
        <span className="text-sm text-iron">{dollars(s.remaining_cents)} left</span>
      </div>

      <div className="h-2 w-full bg-iron/20 rounded-full overflow-hidden mb-4">
        <div
          className={`h-full ${barColor} transition-all`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
        <div>
          <dt className="text-iron">Window</dt>
          <dd className="tabular">{s.window_days}d</dd>
        </div>
        <div>
          <dt className="text-iron">LLM cost</dt>
          <dd className="tabular">{cents(s.llm_cost_cents)}</dd>
        </div>
        {s.declined_count > 0 ? (
          <div>
            <dt className="text-iron">Declined</dt>
            <dd className="tabular text-danger">{s.declined_count}</dd>
          </div>
        ) : null}
      </dl>
    </Card>
  );
}

function dollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function cents(n: number): string {
  if (n === 0) return "0¢";
  if (n < 100) return `${n}¢`;
  return dollars(n);
}
