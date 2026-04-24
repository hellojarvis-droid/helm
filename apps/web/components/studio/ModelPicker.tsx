"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import type { ModelEntry, CanvasTool } from "@/lib/api";

// Bottom-left persistent picker per Krea pattern. Every model chip shows
// three pills — cost / seconds / best-for — and a green "Recommended"
// badge when appropriate. Click to expand full list.

export function ModelPicker({
  tool,
  models,
  value,
  onChange,
}: {
  tool: CanvasTool;
  models: ModelEntry[];
  value: string;
  onChange: (slug: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = models.find((m) => m.slug === value) ?? models[0];
  if (!selected) return null;

  const isRecommended = selected.recommended_for.includes(tool);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-2 rounded-sm border border-rule bg-paper px-3 py-2",
          "hover:border-ink-2 transition-colors",
          open && "border-ink-2",
        )}
      >
        <div className="text-left">
          <div className="flex items-center gap-1.5">
            <span className="text-[13px] font-medium text-ink">{selected.name}</span>
            {isRecommended && (
              <span className="rounded-full bg-sage/20 text-ink px-1.5 py-0.5 text-[9px] uppercase tracking-[0.06em]">
                Rec
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[10px] text-ink-3">
            <Pill>{selected.cost_credits}c</Pill>
            <Pill>~{selected.avg_seconds}s</Pill>
            <Pill>{selected.best_for}</Pill>
          </div>
        </div>
        <span className="text-ink-3 text-[10px]">▾</span>
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-1.5 z-20 w-[340px] rounded-sm border border-rule bg-paper shadow-lg">
          <div className="border-b border-rule px-3 py-2 text-[10px] uppercase tracking-[0.08em] text-ink-3">
            Models · {tool}
          </div>
          <ul className="max-h-[360px] overflow-y-auto">
            {models.map((m) => {
              const active = m.slug === value;
              const rec = m.recommended_for.includes(tool);
              return (
                <li key={m.slug}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(m.slug);
                      setOpen(false);
                    }}
                    className={cn(
                      "w-full text-left px-3 py-2 hover:bg-sand",
                      active && "bg-paper-2",
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-[13px] font-medium text-ink">{m.name}</span>
                      {rec && (
                        <span className="rounded-full bg-sage/20 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.06em]">
                          Rec
                        </span>
                      )}
                      <span className="ml-auto text-[10px] text-ink-3">{m.provider}</span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[10px] text-ink-3">
                      <Pill>{m.cost_credits}c</Pill>
                      <Pill>~{m.avg_seconds}s</Pill>
                      <Pill>{m.best_for}</Pill>
                    </div>
                    {m.description && (
                      <div className="mt-1 text-[11px] text-ink-3 leading-snug">
                        {m.description}
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-sand px-1.5 py-0.5 tabular">{children}</span>
  );
}
