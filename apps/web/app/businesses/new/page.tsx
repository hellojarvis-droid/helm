"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { createBusiness } from "@/lib/api";

const VERTICALS = [
  { value: "dtc_physical", label: "DTC — Physical product" },
  { value: "dtc_pod", label: "DTC — Print-on-demand" },
  { value: "saas", label: "SaaS" },
  { value: "services", label: "Services" },
] as const;

export default function NewBusinessPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [vertical, setVertical] = useState<string>(VERTICALS[0].value);
  const [cap, setCap] = useState(500);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await createBusiness({
        name: name.trim(),
        vertical,
        weekly_spend_cap_cents: cap * 100,
      });
      router.replace("/businesses");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell breadcrumbs={["Helm", "Businesses", "New"]}>
      <div className="max-w-lg mx-auto px-8 py-12">
        <div className="mb-8">
          <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">
            New venture
          </div>
          <h1 className="font-serif text-[36px] leading-tight tracking-tightest mb-2">
            What are you bringing to market?
          </h1>
          <p className="text-sm text-ink-3">
            Name it, pick a vertical, set a weekly cap. Atlas takes it from here.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-6">
          <div className="space-y-2">
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Name
            </label>
            <Input
              required
              minLength={1}
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ember Candles"
            />
          </div>

          <div className="space-y-2">
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Vertical
            </label>
            <select
              className="flex h-10 w-full rounded-sm border border-rule bg-paper px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink-2"
              value={vertical}
              onChange={(e) => setVertical(e.target.value)}
            >
              {VERTICALS.map((v) => (
                <option key={v.value} value={v.value}>
                  {v.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
                Weekly spend cap
              </label>
              <span className="font-serif text-[22px] tabular">${cap}</span>
            </div>
            <input
              type="range"
              min={50}
              max={5000}
              step={50}
              value={cap}
              onChange={(e) => setCap(Number(e.target.value))}
              className="w-full accent-terracotta"
            />
            <p className="text-xs text-ink-3">
              The Stripe-issued card refuses any spend that would push the weekly total past this.
            </p>
          </div>

          {err && <p className="text-sm text-rose-2">{err}</p>}

          <div className="flex gap-2 pt-2">
            <Button type="submit" variant="accent" size="lg" disabled={busy || !name.trim()}>
              {busy ? "Creating…" : "Launch venture"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="lg"
              onClick={() => router.back()}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </AppShell>
  );
}
