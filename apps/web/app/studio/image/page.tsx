"use client";

import { useEffect, useMemo, useState } from "react";
import { ToolCanvas } from "@/components/studio/ToolCanvas";
import { MagnificSlider } from "@/components/studio/MagnificSlider";
import { useGenerationSession } from "@/components/studio/useGenerationSession";
import { cn } from "@/lib/cn";
import {
  listViralPresets,
  type ReferenceChipT,
} from "@/lib/api";
import { useStudio } from "../layout";

const ASPECTS = ["9:16", "1:1", "16:9", "4:5"] as const;

export default function StudioImage() {
  const { businessId } = useStudio();
  const sess = useGenerationSession({ tool: "image", businessId });

  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<ReferenceChipT[]>([]);
  const [aspect, setAspect] = useState<string>("1:1");
  const [creativity, setCreativity] = useState(60);
  const [resemblance, setResemblance] = useState(40);
  const [hdr, setHdr] = useState(50);
  const [seed, setSeed] = useState<string>("");

  const [presets, setPresets] = useState<
    { slug: string; label: string; tool: string; prompt_suffix: string }[]
  >([]);
  useEffect(() => {
    (async () => {
      try {
        const rows = await listViralPresets();
        setPresets(rows.filter((p) => p.tool === "image"));
      } catch {
        // no-op
      }
    })();
  }, []);

  const estimatedCredits = useMemo(() => {
    return sess.selectedModel?.cost_credits ?? 0;
  }, [sess.selectedModel]);

  const params = useMemo(
    () => ({
      aspect_ratio: aspect,
      creativity,
      resemblance,
      hdr,
      ...(seed.trim() ? { seed: Number(seed) } : {}),
    }),
    [aspect, creativity, resemblance, hdr, seed],
  );

  const onGenerate = () => {
    if (!prompt.trim()) return;
    void sess.generate({ prompt: prompt.trim(), params, references: refs });
  };

  return (
    <ToolCanvas
      title="Image"
      subtitle="Text-to-image. Pick the model that matches your look: Flux for photoreal, Ideogram for text-in-image, Midjourney for aesthetic, Nano Banana for fast stills."
      tool="image"
      promptValue={prompt}
      onPromptChange={setPrompt}
      promptPlaceholder="A minimalist linen throw blanket on a sunlit oak chair, warm morning haze."
      references={refs}
      onReferencesChange={setRefs}
      models={sess.models}
      modelSlug={sess.modelSlug}
      onModelChange={sess.setModelSlug}
      estimatedCredits={estimatedCredits}
      onGenerate={onGenerate}
      canGenerate={prompt.trim().length > 0}
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
      presetChips={
        presets.length ? (
          <div className="flex flex-wrap gap-1.5">
            <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3 self-center mr-1">
              Viral presets
            </span>
            {presets.map((p) => (
              <button
                key={p.slug}
                type="button"
                onClick={() => setPrompt((prev) => (prev.trim() ? `${prev}${p.prompt_suffix}` : p.label + p.prompt_suffix))}
                className="rounded-full border border-rule bg-paper-2 px-2 py-0.5 text-[11px] text-ink-2 hover:bg-sand hover:text-ink"
                title={p.prompt_suffix}
              >
                {p.label}
              </button>
            ))}
          </div>
        ) : null
      }
      sidebar={
        <>
          <div>
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
              Aspect
            </div>
            <div className="flex gap-1">
              {ASPECTS.map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => setAspect(a)}
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[11px]",
                    aspect === a
                      ? "bg-ink text-paper border-ink"
                      : "bg-paper text-ink-2 border-rule hover:bg-sand",
                  )}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>

          <MagnificSlider
            label="Creativity"
            helper="How much the AI hallucinates beyond the prompt."
            min={0}
            max={100}
            value={creativity}
            onChange={setCreativity}
            suffix="%"
          />
          <MagnificSlider
            label="Resemblance"
            helper="Higher = stick closer to attached references."
            min={0}
            max={100}
            value={resemblance}
            onChange={setResemblance}
            suffix="%"
          />
          <MagnificSlider
            label="HDR"
            helper="Contrast + highlight punch."
            min={0}
            max={100}
            value={hdr}
            onChange={setHdr}
            suffix="%"
          />

          <div>
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
              Seed (optional)
            </div>
            <input
              type="text"
              inputMode="numeric"
              value={seed}
              onChange={(e) => setSeed(e.target.value.replace(/[^\d]/g, ""))}
              placeholder="leave blank for random"
              className="flex w-full rounded-sm border border-rule bg-paper px-2 py-1.5 text-[13px] font-mono tabular"
            />
            <p className="mt-1 text-[10px] text-ink-3">
              Reuse a seed to reproduce a look.
            </p>
          </div>
        </>
      }
    />
  );
}
