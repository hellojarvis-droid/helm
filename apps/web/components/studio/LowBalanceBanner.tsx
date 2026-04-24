"use client";

// Soft banner at <10% balance; inline overdraw confirm.

export function LowBalanceBanner({
  balanceCents,
  monthlyAllotmentCents,
  onTopUp,
}: {
  balanceCents: number;
  monthlyAllotmentCents: number;
  onTopUp: () => void;
}) {
  if (monthlyAllotmentCents <= 0) return null;
  const pct = balanceCents / monthlyAllotmentCents;
  if (pct > 0.1) return null;
  return (
    <div className="rounded-sm border border-amber/60 bg-amber/10 px-3 py-2 text-[12px] text-ink flex items-center justify-between">
      <span>
        You&rsquo;re at <span className="tabular">${(balanceCents / 100).toFixed(2)}</span> —
        {" "}
        <span className="text-ink-3">under 10% of this month&rsquo;s plan credits.</span>
      </span>
      <button
        type="button"
        onClick={onTopUp}
        className="rounded-sm border border-ink bg-ink px-2 py-0.5 text-[11px] text-paper hover:bg-terracotta hover:border-terracotta"
      >
        Top up
      </button>
    </div>
  );
}
