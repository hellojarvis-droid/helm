"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { CostLiveChip } from "@/components/studio/CostLiveChip";
import { GenerationCard, type ActionKind } from "@/components/studio/GenerationCard";
import { ModelPicker } from "@/components/studio/ModelPicker";
import { PromptBox } from "@/components/studio/PromptBox";
import { ReceiptPanel } from "@/components/studio/ReceiptPanel";
import type { CanvasTool, Generation, ModelEntry, ReferenceChipT } from "@/lib/api";

// Shared per-tool layout:
// ┌───────────────────────────────────────────────────────────────┐
// │ Header: title + tool blurb + reset-session                     │
// ├────────────────────────────┬──────────────────────────────────┤
// │  Prompt + references        │ Params (sliders / presets)       │
// │  Model picker + cost + CTA  │                                  │
// ├────────────────────────────┴──────────────────────────────────┤
// │ Gallery: finished + in-flight generations                     │
// └───────────────────────────────────────────────────────────────┘

export function ToolCanvas(props: {
  title: string;
  subtitle: string;
  tool: CanvasTool;
  promptValue: string;
  onPromptChange: (v: string) => void;
  promptPlaceholder?: string;
  references: ReferenceChipT[];
  onReferencesChange: (refs: ReferenceChipT[]) => void;
  models: ModelEntry[];
  modelSlug: string;
  onModelChange: (slug: string) => void;
  estimatedCredits: number;
  onGenerate: () => void;
  generateLabel?: string;
  canGenerate: boolean;
  busy: boolean;
  error: string | null;
  sidebar?: ReactNode;
  presetChips?: ReactNode;
  gens: Generation[];
  onAction: (gen: Generation, kind: ActionKind) => void;
  onToggleFavorite: (id: string) => void;
  onResetSession: () => void;
}) {
  const selectedModel = props.models.find((m) => m.slug === props.modelSlug);
  return (
    <div className="max-w-[1200px] mx-auto px-8 py-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-[32px] leading-none text-ink">{props.title}</h1>
          <p className="mt-2 text-[13px] text-ink-2 max-w-[65ch]">{props.subtitle}</p>
        </div>
        <button
          type="button"
          onClick={props.onResetSession}
          className="text-[11px] text-ink-3 hover:text-terracotta"
        >
          Start new session
        </button>
      </header>

      {props.error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {props.error}
        </div>
      )}

      <div className="grid grid-cols-12 gap-5 mb-8">
        <div className="col-span-12 lg:col-span-8 space-y-3">
          <PromptBox
            value={props.promptValue}
            onChange={props.onPromptChange}
            placeholder={props.promptPlaceholder}
            references={props.references}
            onReferencesChange={props.onReferencesChange}
            disabled={props.busy}
            rows={4}
          />

          {props.presetChips && <div>{props.presetChips}</div>}

          <div className="flex items-end flex-wrap gap-2">
            <ModelPicker
              tool={props.tool}
              models={props.models}
              value={props.modelSlug}
              onChange={props.onModelChange}
            />
            <div className="ml-auto flex items-center gap-2">
              <CostLiveChip credits={props.estimatedCredits} />
              <Button
                variant="accent"
                size="lg"
                onClick={props.onGenerate}
                disabled={!props.canGenerate || props.busy}
              >
                {props.busy ? "Queuing…" : (props.generateLabel ?? "Generate")}
              </Button>
            </div>
          </div>
          <p className="text-[10px] text-ink-3">
            Failed generations never cost credits.
          </p>
        </div>

        <div className="col-span-12 lg:col-span-4">
          <div className="rounded-sm border border-rule bg-paper-2 p-4 space-y-4">
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
              Settings
            </div>
            {props.sidebar}
          </div>
        </div>
      </div>

      <div className="mb-2 text-[11px] uppercase tracking-[0.08em] text-ink-3">
        Session gallery
      </div>
      {props.gens.length === 0 ? (
        <p className="rounded-sm border border-rule bg-paper-2 p-5 text-center text-[13px] text-ink-3">
          Anything you generate in this session will appear here.
        </p>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {props.gens.map((g) => (
            <div key={g.id} className="space-y-1.5">
              <GenerationCard
                gen={g}
                model={selectedModel && g.model === selectedModel.slug ? selectedModel : props.models.find((m) => m.slug === g.model)}
                onAction={(k) => props.onAction(g, k)}
                onToggleFavorite={() => props.onToggleFavorite(g.id)}
              />
              {g.status === "completed" && (
                <ReceiptPanel
                  gen={g}
                  model={props.models.find((m) => m.slug === g.model)}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
