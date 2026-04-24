"use client";

import { useCallback, useEffect, useState } from "react";
import { TopUpSheet } from "@/components/credits/TopUpSheet";
import { cn } from "@/lib/cn";
import { getCreditBalance, type CreditBalanceState } from "@/lib/api";

// Top-bar chip showing the user's live credit balance. One click opens
// the top-up sheet. Colour darkens as the balance drops so it's a
// passive nag before it's an active block.
export function BalanceChip() {
  const [state, setState] = useState<CreditBalanceState | null>(null);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const s = await getCreditBalance();
      setState(s);
    } catch {
      // Silent — unauthed view, network blip, etc. The chip hides.
    }
  }, []);

  useEffect(() => {
    void refresh();
    // Poll every 30s so buy-credits → balance updates feel live
    // without hammering the API.
    const iv = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(iv);
  }, [refresh]);

  if (state === null) return null;

  const dollars = (state.balance_cents / 100).toFixed(2);
  const tone =
    state.balance_cents <= 0
      ? "chip-rose"
      : state.balance_cents < 500
        ? "chip-amber"
        : "";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "chip flex items-center gap-1.5 px-2.5 py-1.5 text-[12px] hover:opacity-80 transition-opacity",
          tone,
        )}
        title="Credits · click to top up"
      >
        <span className="font-mono tabular">${dollars}</span>
        <span className="text-[10px] uppercase tracking-[0.06em]">credits</span>
      </button>
      <TopUpSheet
        open={open}
        onClose={() => setOpen(false)}
        minTopUpCents={state.min_top_up_cents}
        onSuccess={() => {
          void refresh();
        }}
      />
    </>
  );
}
