"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  quoteTopUp,
  startTopUp,
  type PaymentMethod,
  type TopUpQuote,
} from "@/lib/api";

// Modal for purchasing credits. Shows a live fee quote from the API so
// the UI preview and the Stripe Checkout total agree to the cent.
//
// Design intent: Stripe's card fee (~4.4% on a $20 top-up after the
// fixed $0.30) is uncomfortably visible if we stay on cards. The sheet
// nudges users toward ACH (0.8% capped at $5) when the saving is
// meaningful by showing both lines side-by-side.

interface Props {
  open: boolean;
  onClose: () => void;
  minTopUpCents: number;
  onSuccess?: () => void;
}

const AMOUNT_PRESETS_CENTS = [2000, 5000, 10_000, 25_000, 50_000];

export function TopUpSheet({ open, onClose, minTopUpCents, onSuccess }: Props) {
  const [creditCents, setCreditCents] = useState(2000);
  const [method, setMethod] = useState<PaymentMethod>("card");
  const [quote, setQuote] = useState<TopUpQuote | null>(null);
  const [altQuote, setAltQuote] = useState<TopUpQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Fetch both methods' quotes on every change so the sheet can show
  // the side-by-side compare card. Debounced at 150ms for typing.
  const refresh = useCallback(async () => {
    if (creditCents < minTopUpCents) {
      setQuote(null);
      setAltQuote(null);
      return;
    }
    setErr(null);
    try {
      const [card, ach] = await Promise.all([
        quoteTopUp({ credit_amount_cents: creditCents, payment_method: "card" }),
        quoteTopUp({ credit_amount_cents: creditCents, payment_method: "us_bank_account" }),
      ]);
      if (method === "card") {
        setQuote(card);
        setAltQuote(ach);
      } else {
        setQuote(ach);
        setAltQuote(card);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [creditCents, method, minTopUpCents]);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [open, refresh]);

  const savings = useMemo(() => {
    if (!quote || !altQuote) return 0;
    return quote.total_charge_cents - altQuote.total_charge_cents;
  }, [quote, altQuote]);

  async function go() {
    if (!quote) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await startTopUp({
        credit_amount_cents: quote.credit_amount_cents,
        payment_method: quote.payment_method,
      });
      onSuccess?.();
      // Full-page redirect so popup blockers don't kill the checkout.
      window.location.href = res.url;
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  if (!open) return null;

  const belowMin = creditCents < minTopUpCents;

  return (
    <div
      className="fixed inset-0 z-[70] bg-ink/40 backdrop-blur-sm grid place-items-center p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="bg-paper rounded-xl border border-rule shadow-lg w-full max-w-lg p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-5">
          <div className="h-9 w-9 grid place-items-center rounded-md bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-base leading-none shrink-0">
            $
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-[17px] font-semibold">Top up credits</h2>
            <p className="text-[12.5px] text-ink-3 mt-0.5">
              You receive exactly the credit amount you pick. Stripe&apos;s processing fee
              is charged on top and shown transparently below.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-7 w-7 grid place-items-center rounded-sm text-ink-3 hover:bg-sand hover:text-ink"
            aria-label="Close"
          >
            <Icon name="close" size={12} />
          </button>
        </div>

        <div className="space-y-5">
          <div>
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Amount of credits to add
            </label>
            <div className="mt-2 flex flex-wrap gap-2">
              {AMOUNT_PRESETS_CENTS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCreditCents(c)}
                  className={cn(
                    "px-3 py-1.5 rounded-full text-[12.5px] border transition-colors",
                    creditCents === c
                      ? "bg-ink text-paper border-ink"
                      : "bg-paper text-ink-2 border-rule hover:bg-sand",
                  )}
                >
                  ${(c / 100).toFixed(0)}
                </button>
              ))}
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-[13px] text-ink-3 font-mono">$</span>
                <input
                  type="number"
                  min={minTopUpCents / 100}
                  step="1"
                  value={(creditCents / 100).toFixed(0)}
                  onChange={(e) => {
                    const dollars = Number(e.target.value);
                    if (Number.isFinite(dollars) && dollars >= 0) {
                      setCreditCents(Math.round(dollars * 100));
                    }
                  }}
                  className="w-24 h-9 rounded-sm border border-rule bg-paper px-2.5 text-[13px] text-ink font-mono focus:outline-none focus:border-ink-2"
                />
              </div>
            </div>
            {belowMin && (
              <p className="text-[11.5px] text-rose-2 mt-2">
                Minimum top-up is ${(minTopUpCents / 100).toFixed(0)}.
              </p>
            )}
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium mb-2">
              Payment method
            </div>
            <div className="grid grid-cols-2 gap-2">
              <MethodOption
                label="Credit/debit card"
                hint="Instant. Higher Stripe fee (2.9% + $0.30)."
                selected={method === "card"}
                onClick={() => setMethod("card")}
              />
              <MethodOption
                label="Bank transfer (ACH)"
                hint="Lower fee (0.8%, $5 cap). Takes 1–4 business days."
                selected={method === "us_bank_account"}
                onClick={() => setMethod("us_bank_account")}
              />
            </div>
          </div>

          {quote && (
            <div className="rounded-md border border-rule bg-paper-2 p-4 space-y-2">
              <Row
                label="Credits to your balance"
                value={`$${(quote.credit_amount_cents / 100).toFixed(2)}`}
              />
              <Row
                label="Stripe processing fee"
                value={`+ $${(quote.fee_cents / 100).toFixed(2)}`}
                hint={quote.fee_explanation}
              />
              <div className="border-t border-rule pt-2 mt-1">
                <Row
                  label={`Total charged to ${
                    quote.payment_method === "card" ? "your card" : "your bank"
                  }`}
                  value={`$${(quote.total_charge_cents / 100).toFixed(2)}`}
                  emphasise
                />
              </div>
              {altQuote && savings !== 0 && (
                <p className="text-[11.5px] text-ink-3 leading-relaxed pt-2">
                  {savings > 0 ? (
                    <>
                      Using{" "}
                      <button
                        type="button"
                        onClick={() =>
                          setMethod(
                            quote.payment_method === "card"
                              ? "us_bank_account"
                              : "card",
                          )
                        }
                        className="text-terracotta-2 hover:underline"
                      >
                        {quote.payment_method === "card"
                          ? "a bank transfer"
                          : "a card"}
                      </button>{" "}
                      saves ${(Math.abs(savings) / 100).toFixed(2)} in fees.
                    </>
                  ) : null}
                </p>
              )}
            </div>
          )}

          {err && (
            <div className="rounded-md border border-rose-2/50 bg-rose-soft/50 p-3 text-[13px] text-rose-2">
              {err}
            </div>
          )}

          <div className="flex gap-2 justify-end pt-1">
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="accent"
              onClick={() => void go()}
              disabled={busy || belowMin || !quote}
            >
              {busy ? "Opening Stripe…" : "Buy credits"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MethodOption({
  label,
  hint,
  selected,
  onClick,
}: {
  label: string;
  hint: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "text-left rounded-sm border p-3 transition-colors",
        selected
          ? "bg-terracotta-soft/40 border-terracotta"
          : "bg-paper border-rule hover:bg-sand",
      )}
    >
      <div className="text-[13px] font-medium">{label}</div>
      <div className="text-[11.5px] text-ink-3 mt-1 leading-relaxed">{hint}</div>
    </button>
  );
}

function Row({
  label,
  value,
  hint,
  emphasise,
}: {
  label: string;
  value: string;
  hint?: string;
  emphasise?: boolean;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span
          className={cn(
            "text-[13px]",
            emphasise ? "font-medium text-ink" : "text-ink-2",
          )}
        >
          {label}
        </span>
        <span
          className={cn(
            "font-mono tabular",
            emphasise ? "text-[15px] text-ink" : "text-[13px] text-ink-2",
          )}
        >
          {value}
        </span>
      </div>
      {hint && <p className="text-[11px] text-ink-3 mt-1 leading-snug">{hint}</p>}
    </div>
  );
}
