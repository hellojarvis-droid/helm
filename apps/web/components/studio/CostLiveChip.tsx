"use client";

import { cn } from "@/lib/cn";

// Live pre-generate cost readout, updates as model / params change.
// Pairs with the Generate button.

export function CostLiveChip({
  credits,
  tone = "neutral",
  hint,
}: {
  credits: number;
  tone?: "neutral" | "warn";
  hint?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px]",
        tone === "warn"
          ? "border-amber bg-amber/10 text-ink"
          : "border-rule bg-paper-2 text-ink-2",
      )}
      title={hint}
    >
      <span className="font-mono tabular">~{credits}</span>
      <span className="text-ink-3">credits</span>
      {tone === "warn" && hint && <span className="text-ink-3">· {hint}</span>}
    </div>
  );
}
