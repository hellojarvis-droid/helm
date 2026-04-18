"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { updateBusiness, type BusinessDetail } from "@/lib/api";

interface Props {
  business: BusinessDetail;
  onClose: () => void;
  onSaved: (updated: BusinessDetail) => void;
}

export function EditCapsModal({ business, onClose, onSaved }: Props) {
  const [weekly, setWeekly] = useState((business.weekly_spend_cap_cents / 100).toFixed(0));
  const [perAuth, setPerAuth] = useState((business.per_auth_cap_cents / 100).toFixed(0));
  const [mcc, setMcc] = useState(business.allowed_mcc_codes?.join(", ") ?? "");
  const initialCustomMcc = business.allowed_mcc_codes !== null;
  const [useDefault, setUseDefault] = useState(!initialCustomMcc);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const weeklyCents = Math.round(Number(weekly) * 100);
    const perAuthCents = Math.round(Number(perAuth) * 100);
    if (!Number.isFinite(weeklyCents) || weeklyCents < 0) {
      setError("Weekly cap must be a non-negative number.");
      return;
    }
    if (!Number.isFinite(perAuthCents) || perAuthCents < 0) {
      setError("Per-auth cap must be a non-negative number.");
      return;
    }
    const body: Parameters<typeof updateBusiness>[1] = {
      weekly_spend_cap_cents: weeklyCents,
      per_auth_cap_cents: perAuthCents,
    };
    if (useDefault) {
      body.reset_mcc_codes_to_default = true;
    } else {
      const codes = mcc
        .split(/[\s,]+/)
        .map((c) => c.trim())
        .filter(Boolean);
      if (codes.some((c) => !/^\d{3,4}$/.test(c))) {
        setError("MCC codes must be 3-4 digit numbers.");
        return;
      }
      body.allowed_mcc_codes = codes;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await updateBusiness(business.id, body);
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-6 z-10">
      <div className="bg-paper dark:bg-ink rounded-xl border border-iron/20 p-6 max-w-md w-full">
        <h2 className="text-lg font-semibold mb-1">Edit spend caps</h2>
        <p className="text-sm text-iron mb-5">
          Caps are enforced at our authorization webhook AND on the Stripe card itself. Changes push
          to both.
        </p>

        <div className="space-y-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-iron font-semibold">
              Weekly cap
            </span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-2xl tabular">$</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={weekly}
                onChange={(e) => setWeekly(e.target.value)}
                className="flex-1 bg-haze dark:bg-haze/10 border border-iron/20 rounded-md px-3 py-2 text-base tabular"
              />
            </div>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wider text-iron font-semibold">
              Per-authorization cap
            </span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-2xl tabular">$</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={perAuth}
                onChange={(e) => setPerAuth(e.target.value)}
                className="flex-1 bg-haze dark:bg-haze/10 border border-iron/20 rounded-md px-3 py-2 text-base tabular"
              />
            </div>
          </label>

          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-xs uppercase tracking-wider text-iron font-semibold">
                Allowed MCC codes
              </span>
              <label className="text-xs text-iron flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={useDefault}
                  onChange={(e) => setUseDefault(e.target.checked)}
                />
                Use default allowlist
              </label>
            </div>
            <input
              type="text"
              inputMode="numeric"
              value={mcc}
              onChange={(e) => setMcc(e.target.value)}
              disabled={useDefault}
              placeholder="5734, 7372, 7311"
              className="w-full mt-1 bg-haze dark:bg-haze/10 border border-iron/20 rounded-md px-3 py-2 text-sm font-mono disabled:opacity-50"
            />
            <p className="text-xs text-iron mt-1">
              Comma-separated 4-digit MCC codes. Leave blank + check &ldquo;Use default&rdquo; to
              fall back to the platform allowlist (SaaS, ads, POD suppliers).
            </p>
          </div>

          {error ? <p className="text-sm text-danger">{error}</p> : null}

          <div className="flex gap-2 justify-end pt-2">
            <Button variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button variant="accent" onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
