"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { listBusinesses, type Business } from "@/lib/api";

export default function BusinessesPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Business[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listBusinesses()
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <AppShell breadcrumbs={["Helm", "Businesses"]}>
      <div className="px-10 pt-8 pb-20">
        <div className="flex items-end justify-between mb-7">
          <div>
            <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
              Businesses
            </h1>
            <p className="text-sm text-ink-3">
              Every venture you run. One Stripe-issued card per business, weekly cap enforced.
            </p>
          </div>
          <Button variant="accent" size="lg" onClick={() => router.push("/businesses/new")}>
            <Icon name="plus" size={13} /> New venture
          </Button>
        </div>

        {error && <div className="text-sm text-rose-2 mb-4">{error}</div>}

        {rows === null ? (
          <div className="text-sm text-ink-3">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="rounded-md border border-rule bg-paper p-8 max-w-xl">
            <div className="font-serif text-[24px] leading-tight mb-2">No businesses yet.</div>
            <p className="text-sm text-ink-3 mb-5">
              Start one — the CEO Agent will help you pick an idea, brand it, and launch the
              storefront.
            </p>
            <Button variant="accent" onClick={() => router.push("/businesses/new")}>
              <Icon name="plus" size={13} /> Create your first
            </Button>
          </div>
        ) : (
          <div className="rounded-md border border-rule bg-paper p-[22px]">
            <div className="text-[13px] font-medium text-ink-2 mb-3.5 flex items-center justify-between">
              Portfolio
              <span className="chip">{rows.length} active</span>
            </div>
            <div className="flex flex-col">
              {rows.map((b) => (
                <Link
                  key={b.id}
                  href={`/businesses/${b.id}`}
                  className={cn(
                    "grid items-center gap-3 py-3 border-b border-rule last:border-b-0 hover:bg-sand transition-colors px-2 -mx-2 rounded-sm",
                  )}
                  style={{ gridTemplateColumns: "1fr 140px 120px 100px 24px" }}
                >
                  <div>
                    <div className="text-[14px] font-medium">{b.name}</div>
                    <div className="text-[11px] text-ink-3 mt-0.5">
                      {prettyVertical(b.vertical)}
                    </div>
                  </div>
                  <span
                    className={cn(
                      "chip",
                      b.status === "live"
                        ? "chip-sage"
                        : b.status === "launching"
                          ? "chip-amber"
                          : "",
                    )}
                  >
                    {b.status}
                  </span>
                  <div className="font-mono text-[12px] text-ink-2">
                    ${(b.weekly_spend_cap_cents / 100).toFixed(0)}
                    <span className="text-ink-3">/wk cap</span>
                  </div>
                  <div className="font-mono text-[12px] text-ink-3">
                    {new Date(b.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </div>
                  <Icon name="more" size={14} />
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function prettyVertical(v: string) {
  const MAP: Record<string, string> = {
    dtc_physical: "DTC · physical",
    dtc_pod: "DTC · print-on-demand",
    saas: "SaaS",
    services: "Services",
  };
  return MAP[v] ?? v;
}
