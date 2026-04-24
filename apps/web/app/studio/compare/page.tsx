"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { GenerationCard } from "@/components/studio/GenerationCard";
import { PromptBox } from "@/components/studio/PromptBox";
import { cn } from "@/lib/cn";
import {
  compareGenerations,
  getGeneration,
  InsufficientCreditsError,
  listModels,
  type CanvasTool,
  type Generation,
  type ModelEntry,
  type ReferenceChipT,
} from "@/lib/api";
import { useStudio } from "../layout";

const TOOLS: CanvasTool[] = ["image", "video"];

function newUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export default function ComparePage() {
  const { businessId } = useStudio();
  const [tool, setTool] = useState<CanvasTool>("image");
  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<ReferenceChipT[]>([]);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [gens, setGens] = useState<Generation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const list = await listModels(tool);
        setModels(list);
        // Default-pick top 3 models.
        const initial: Record<string, boolean> = {};
        list.slice(0, 3).forEach((m) => (initial[m.slug] = true));
        setPicked(initial);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [tool]);

  const pickedCount = useMemo(
    () => Object.values(picked).filter(Boolean).length,
    [picked],
  );
  const pickedModels = models.filter((m) => picked[m.slug]);
  const pickedSum = pickedModels.reduce((acc, m) => acc + m.cost_credits, 0);

  const onRun = async () => {
    if (!prompt.trim() || pickedCount < 2 || pickedCount > 4) return;
    setBusy(true);
    setError(null);
    try {
      const result = await compareGenerations({
        business_id: businessId,
        session_id: newUuid(),
        tool,
        models: pickedModels.map((m) => m.slug),
        prompt: prompt.trim(),
        references: refs,
      });
      setGens(result);
    } catch (e) {
      if (e instanceof InsufficientCreditsError) {
        setError(
          `Not enough credits — need $${(e.needed_cents / 100).toFixed(2)}.`,
        );
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  // Poll until every gen is terminal.
  useEffect(() => {
    if (gens.length === 0) return;
    const anyRunning = gens.some(
      (g) => g.status === "pending" || g.status === "queued" || g.status === "running",
    );
    if (!anyRunning) return;
    const iv = setInterval(async () => {
      const next = await Promise.all(gens.map((g) => getGeneration(g.id).catch(() => g)));
      setGens(next);
    }, 4000);
    return () => clearInterval(iv);
  }, [gens]);

  return (
    <div className="max-w-[1200px] mx-auto px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[28px] leading-none text-ink">Compare</h1>
        <p className="mt-2 text-[13px] text-ink-2 max-w-[65ch]">
          Same prompt, 2–4 models side by side. Pick the one whose
          aesthetic fits before committing more credits.
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </div>
      )}

      <section className="mb-6 space-y-3">
        <div className="flex gap-1.5">
          {TOOLS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => {
                setTool(t);
                setGens([]);
              }}
              className={cn(
                "rounded-full border px-3 py-1 text-[12px]",
                tool === t
                  ? "bg-ink text-paper border-ink"
                  : "bg-paper text-ink-2 border-rule hover:bg-sand",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        <PromptBox
          value={prompt}
          onChange={setPrompt}
          placeholder="A linen throw blanket on a sunlit oak chair"
          references={refs}
          onReferencesChange={setRefs}
          disabled={busy}
          rows={3}
        />

        <div>
          <div className="mb-1 text-[11px] uppercase tracking-[0.06em] text-ink-3">
            Models to compare (2–4)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {models.map((m) => {
              const on = !!picked[m.slug];
              return (
                <button
                  key={m.slug}
                  type="button"
                  onClick={() => setPicked((prev) => ({ ...prev, [m.slug]: !prev[m.slug] }))}
                  className={cn(
                    "rounded-sm border px-2.5 py-1 text-[12px]",
                    on
                      ? "bg-ink text-paper border-ink"
                      : "bg-paper text-ink-2 border-rule hover:bg-sand",
                  )}
                >
                  {m.name}
                  <span className={cn("ml-1 text-[10px]", on ? "text-paper/70" : "text-ink-3")}>
                    {m.cost_credits}c
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[11px] text-ink-3 tabular">
            {pickedCount} model{pickedCount === 1 ? "" : "s"} · ~{pickedSum} credits total
          </span>
          <Button
            variant="accent"
            onClick={onRun}
            disabled={!prompt.trim() || pickedCount < 2 || pickedCount > 4 || busy}
          >
            {busy ? "Queuing…" : "Run compare"}
          </Button>
        </div>
      </section>

      {gens.length > 0 && (
        <section>
          <div className="mb-3 text-[11px] uppercase tracking-[0.08em] text-ink-3">
            Results
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {gens.map((g) => (
              <GenerationCard
                key={g.id}
                gen={g}
                model={models.find((m) => m.slug === g.model)}
                onAction={() => {}}
                onToggleFavorite={() => {}}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
