"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Nav } from "@/components/Nav";
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
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-md mx-auto px-6 py-8">
        <h1 className="text-xl font-semibold tracking-tight mb-6">New business</h1>

        <form onSubmit={submit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-sm">Name</label>
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
            <label className="text-sm">Vertical</label>
            <select
              className="flex h-10 w-full rounded-md border border-iron/30 bg-transparent px-3 py-2 text-sm"
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
            <label className="text-sm flex items-center justify-between">
              <span>Weekly spend cap</span>
              <span className="tabular text-iron">${cap}/wk</span>
            </label>
            <input
              type="range"
              min={50}
              max={5000}
              step={50}
              value={cap}
              onChange={(e) => setCap(Number(e.target.value))}
              className="w-full accent-[var(--tw-accent,theme(colors.accent))]"
            />
            <p className="text-xs text-iron">
              The Stripe-issued card will refuse any spend that would push weekly total past this.
            </p>
          </div>

          {err && <p className="text-sm text-danger">{err}</p>}

          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !name.trim()}>
              {busy ? "Creating…" : "Create"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.back()} disabled={busy}>
              Cancel
            </Button>
          </div>
        </form>
      </main>
    </div>
  );
}
