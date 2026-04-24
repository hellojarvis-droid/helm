"use client";

import { useState } from "react";
import type { Generation, ModelEntry } from "@/lib/api";

// Post-generation receipt — click-to-copy settings so users can
// reproduce a result. Research: "never lie about what ran."

export function ReceiptPanel({
  gen,
  model,
}: {
  gen: Generation;
  model?: ModelEntry;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (gen.status !== "completed") return null;

  const seed = (gen.params as Record<string, unknown>)?.seed;
  const cost = gen.cost_cents_actual ?? gen.cost_cents_reserved ?? 0;

  const summary = [
    model?.name ?? gen.model,
    `${cost} credits`,
    seed != null ? `seed ${String(seed)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const receiptBlob = {
    model: gen.model,
    provider: model?.provider,
    tool: gen.tool,
    prompt: gen.prompt,
    params: gen.params,
    references: gen.references,
    cost_credits: cost,
    generation_id: gen.id,
  };

  const onCopy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(receiptBlob, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="rounded-sm border border-rule bg-paper-2 text-[11px] text-ink-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-1.5 hover:bg-sand"
      >
        <span>Receipt · {summary}</span>
        <span className="text-ink-3">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="border-t border-rule px-3 py-2 space-y-1.5">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
            <dt className="text-ink-3">Model</dt>
            <dd className="text-ink-2">
              {model?.name ?? gen.model}
              {model && <span className="text-ink-3"> · {model.provider}</span>}
            </dd>
            <dt className="text-ink-3">Tool</dt>
            <dd className="text-ink-2">{gen.tool}</dd>
            <dt className="text-ink-3">Credits</dt>
            <dd className="text-ink-2 tabular">{cost}</dd>
            {seed != null && (
              <>
                <dt className="text-ink-3">Seed</dt>
                <dd className="text-ink-2 tabular">{String(seed)}</dd>
              </>
            )}
            <dt className="text-ink-3">Generation</dt>
            <dd className="text-ink-2 font-mono">{gen.id.slice(0, 8)}</dd>
          </dl>
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={onCopy}
              className="rounded-sm border border-rule bg-paper px-2 py-0.5 text-[10px] hover:bg-sand"
            >
              {copied ? "Copied" : "Copy settings"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
