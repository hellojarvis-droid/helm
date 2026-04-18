"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Nav } from "@/components/Nav";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { type BusinessToday, getToday, type TodaySummary } from "@/lib/api";

export default function TodayPage() {
  const [data, setData] = useState<TodaySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getToday()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        {!data && !error ? <p className="text-sm text-iron">Loading…</p> : null}

        {data ? (
          <>
            <header>
              <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-1">
                Net last 24h
              </div>
              <div
                className={cn(
                  "text-5xl font-semibold tabular",
                  data.net_today_cents >= 0 ? "text-success" : "text-danger",
                )}
              >
                {data.net_today_cents >= 0 ? "+" : "−"}$
                {(Math.abs(data.net_today_cents) / 100).toFixed(2)}
              </div>
              <div className="mt-2 text-sm text-iron tabular flex gap-4">
                <span>+${(data.revenue_today_cents / 100).toFixed(2)} revenue</span>
                <span>−${(data.spend_today_cents / 100).toFixed(2)} spend</span>
              </div>
            </header>

            {data.pending_approval_count > 0 ? (
              <Link
                href={{ pathname: "/approvals" }}
                className="block bg-accent text-paper rounded-lg px-4 py-3 text-sm font-semibold hover:bg-accent/90"
              >
                {data.pending_approval_count} approval
                {data.pending_approval_count === 1 ? "" : "s"} waiting on you →
              </Link>
            ) : null}

            <section>
              <h2 className="text-xs font-semibold tracking-widest text-iron uppercase mb-3">
                Businesses
              </h2>
              {data.businesses.length === 0 ? (
                <Card>
                  <p className="text-sm text-iron">
                    No businesses yet. Create one to give the CEO Agent something to work on.
                  </p>
                </Card>
              ) : (
                <ul className="space-y-2">
                  {data.businesses.map((b) => (
                    <BusinessRow key={b.id} biz={b} />
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

function BusinessRow({ biz }: { biz: BusinessToday }) {
  const netPositive = biz.net_today_cents >= 0;
  return (
    <li>
      <Link
        href={`/businesses/${biz.id}` as never}
        className="flex items-center gap-4 bg-haze/40 dark:bg-ink/40 border border-iron/20 rounded-lg px-4 py-3 hover:border-iron/40 transition-colors"
      >
        <div className="flex-1">
          <div className="text-sm font-medium">{biz.name}</div>
          <div className="text-xs text-iron">
            {biz.vertical} · {biz.status}
          </div>
        </div>
        <div className="text-right">
          <div
            className={cn(
              "text-lg font-semibold tabular",
              netPositive ? "text-success" : "text-danger",
            )}
          >
            {netPositive ? "+" : "−"}${(Math.abs(biz.net_today_cents) / 100).toFixed(0)}
          </div>
          {biz.pending_approval_count > 0 ? (
            <div className="text-xs font-semibold text-accent">
              ● {biz.pending_approval_count} approval
            </div>
          ) : (
            <div className="text-xs text-iron tabular">
              ${(biz.revenue_today_cents / 100).toFixed(0)}r · $
              {(biz.spend_today_cents / 100).toFixed(0)}s
            </div>
          )}
        </div>
      </Link>
    </li>
  );
}
