"use client";

import { useMemo, useState } from "react";
import { ToolCanvas } from "@/components/studio/ToolCanvas";
import { useGenerationSession } from "@/components/studio/useGenerationSession";
import { cn } from "@/lib/cn";
import type { ReferenceChipT } from "@/lib/api";
import { useStudio } from "../layout";

const FACTORS = [2, 4];

export default function StudioEnhance() {
  const { businessId } = useStudio();
  const sess = useGenerationSession({ tool: "enhance", businessId });

  const [refs, setRefs] = useState<ReferenceChipT[]>([]);
  const [factor, setFactor] = useState<number>(4);

  const estimatedCredits = useMemo(() => {
    const base = sess.selectedModel?.cost_credits ?? 0;
    return Math.max(1, Math.round((base * factor) / 4));
  }, [sess.selectedModel, factor]);

  const hasSource = refs.length > 0;

  const onGenerate = () => {
    if (!hasSource) return;
    void sess.generate({
      prompt: "Upscale the attached image cleanly, no new detail hallucination.",
      params: { upscale_factor: factor },
      references: refs,
    });
  };

  return (
    <ToolCanvas
      title="Enhance"
      subtitle="Upscale any image or video. Attach the source as a Describe reference, pick a factor, regenerate at higher resolution."
      tool="enhance"
      promptValue={""}
      onPromptChange={() => {}}
      references={refs}
      onReferencesChange={setRefs}
      models={sess.models}
      modelSlug={sess.modelSlug}
      onModelChange={sess.setModelSlug}
      estimatedCredits={estimatedCredits}
      onGenerate={onGenerate}
      generateLabel={hasSource ? "Enhance" : "Attach an image first"}
      canGenerate={hasSource}
      busy={sess.busy}
      error={sess.error}
      gens={sess.gens}
      onAction={async (gen, kind) => {
        if (kind === "use_as_reference") {
          if (gen.output_url)
            setRefs((prev) => [
              ...prev,
              { url: gen.output_url!, role: "describe", label: "From output" },
            ]);
          return;
        }
        await sess.action(gen.id, kind);
      }}
      onToggleFavorite={sess.toggleFavorite}
      onResetSession={sess.resetSession}
      sidebar={
        <>
          <p className="text-[11px] text-ink-3 leading-relaxed">
            Enhance takes the <b>Describe</b> reference and upscales it.
            The cost scales with the factor.
          </p>
          <div>
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
              Factor
            </div>
            <div className="flex gap-1">
              {FACTORS.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFactor(f)}
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[11px]",
                    factor === f
                      ? "bg-ink text-paper border-ink"
                      : "bg-paper text-ink-2 border-rule hover:bg-sand",
                  )}
                >
                  {f}x
                </button>
              ))}
            </div>
          </div>
        </>
      }
    />
  );
}
