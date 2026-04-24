"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { getUsage, type UsageResponse } from "@/lib/api";

export default function UsagePage() {
  const [data, setData] = useState<UsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getUsage());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="max-w-[1000px] mx-auto px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[28px] leading-none text-ink">Usage</h1>
        <p className="mt-2 text-[13px] text-ink-2 max-w-[60ch]">
          Every model, every run, what it cost, what it took. Real
          numbers from your own generations — no ambiguous
          &ldquo;unlimited&rdquo; marketing.
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </div>
      )}

      {!data ? (
        <div className="text-[13px] text-ink-3">Loading…</div>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3">
            <Tile label="Total generations" value={data.totals.count.toString()} />
            <Tile
              label="Total cost"
              value={`$${(data.totals.cost_cents / 100).toFixed(2)}`}
            />
          </div>

          {data.per_model.length === 0 ? (
            <div className="rounded-sm border border-rule bg-paper-2 p-6 text-center text-[13px] text-ink-3">
              No completed generations yet.
            </div>
          ) : (
            <div className="rounded-sm border border-rule bg-paper overflow-hidden">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-rule text-left text-[11px] uppercase tracking-[0.06em] text-ink-3">
                    <th className="px-3 py-2">Tool</th>
                    <th className="px-3 py-2">Model</th>
                    <th className="px-3 py-2 text-right">Runs</th>
                    <th className="px-3 py-2 text-right">Cost</th>
                    <th className="px-3 py-2 text-right">Avg latency</th>
                    <th className="px-3 py-2">Last used</th>
                  </tr>
                </thead>
                <tbody>
                  {data.per_model.map((r) => (
                    <tr key={`${r.tool}-${r.model}`} className="border-b border-rule last:border-b-0">
                      <td className="px-3 py-2">
                        <span className="rounded-full bg-sand px-1.5 py-0.5 text-[10px] uppercase tracking-wider">
                          {r.tool}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-medium">{r.model}</td>
                      <td className="px-3 py-2 text-right tabular">{r.count}</td>
                      <td className="px-3 py-2 text-right tabular">
                        ${(r.total_cost_cents / 100).toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right tabular text-ink-3">
                        {r.avg_seconds ? `${r.avg_seconds.toFixed(1)}s` : "—"}
                      </td>
                      <td className="px-3 py-2 text-ink-3">
                        {r.last_used ? new Date(r.last_used).toLocaleString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="mt-5 text-[11px] text-ink-3">
            Failed generations never cost credits. Deprecated models stay
            listed — when a provider retires a version we give 2–4 weeks
            notice and keep the pinnable one on higher tiers.
          </p>
        </>
      )}
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-rule bg-paper-2 p-4">
      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-3">{label}</div>
      <div className={cn("mt-1 font-serif text-[28px] text-ink tabular")}>{value}</div>
    </div>
  );
}
