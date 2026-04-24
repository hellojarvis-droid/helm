"use client";

import { useEffect, useMemo, useState } from "react";
import { MagnificSlider } from "@/components/studio/MagnificSlider";
import { ToolCanvas } from "@/components/studio/ToolCanvas";
import { useGenerationSession } from "@/components/studio/useGenerationSession";
import { cn } from "@/lib/cn";
import { listCameraPresets, listViralPresets, type ReferenceChipT } from "@/lib/api";
import { useStudio } from "../layout";

const ASPECTS = ["9:16", "1:1", "16:9", "4:5"] as const;

export default function StudioVideo() {
  const { businessId } = useStudio();
  const sess = useGenerationSession({ tool: "video", businessId });

  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<ReferenceChipT[]>([]);
  const [aspect, setAspect] = useState<string>("9:16");
  const [duration, setDuration] = useState(5);
  const [motion, setMotion] = useState(60);
  const [cameraSuffix, setCameraSuffix] = useState<string>("");

  const [viral, setViral] = useState<
    { slug: string; label: string; prompt_suffix: string }[]
  >([]);
  const [cameras, setCameras] = useState<
    { slug: string; label: string; prompt_suffix: string }[]
  >([]);
  useEffect(() => {
    (async () => {
      try {
        const [v, c] = await Promise.all([listViralPresets(), listCameraPresets()]);
        setViral(v.filter((p) => p.tool === "video"));
        setCameras(c);
      } catch {
        // ignore
      }
    })();
  }, []);

  const estimatedCredits = useMemo(() => {
    const base = sess.selectedModel?.cost_credits ?? 0;
    return Math.max(1, Math.round((base * duration) / 5));
  }, [sess.selectedModel, duration]);

  const params = useMemo(
    () => ({
      aspect_ratio: aspect,
      duration_seconds: duration,
      motion,
      camera_suffix: cameraSuffix,
    }),
    [aspect, duration, motion, cameraSuffix],
  );

  const onGenerate = () => {
    const body = (prompt + (cameraSuffix || "")).trim();
    if (!body) return;
    void sess.generate({ prompt: body, params, references: refs });
  };

  return (
    <ToolCanvas
      title="Video"
      subtitle="Text-to-video. Runway is reliable default; Veo for dialogue + audio; Kling for stylized motion; Higgsfield for product hero shots; Sora for complex physics."
      tool="video"
      promptValue={prompt}
      onPromptChange={setPrompt}
      promptPlaceholder="A 5-second vertical reel: hands fold a linen blanket onto a linen-draped oak chair, warm morning light."
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
        <div className="space-y-2">
          {cameras.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3 self-center mr-1">
                Camera motion
              </span>
              {cameras.map((c) => {
                const active = cameraSuffix === c.prompt_suffix;
                return (
                  <button
                    key={c.slug}
                    type="button"
                    onClick={() =>
                      setCameraSuffix((prev) =>
                        prev === c.prompt_suffix ? "" : c.prompt_suffix,
                      )
                    }
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[11px]",
                      active
                        ? "bg-ink text-paper border-ink"
                        : "bg-paper-2 text-ink-2 border-rule hover:bg-sand",
                    )}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>
          )}
          {viral.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.06em] text-ink-3 self-center mr-1">
                Viral presets
              </span>
              {viral.map((p) => (
                <button
                  key={p.slug}
                  type="button"
                  onClick={() =>
                    setPrompt((prev) =>
                      prev.trim() ? `${prev}${p.prompt_suffix}` : p.label + p.prompt_suffix,
                    )
                  }
                  className="rounded-full border border-rule bg-paper-2 px-2 py-0.5 text-[11px] text-ink-2 hover:bg-sand hover:text-ink"
                >
                  {p.label}
                </button>
              ))}
            </div>
          )}
        </div>
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
            label="Duration"
            helper="How long the clip runs."
            min={3}
            max={12}
            value={duration}
            onChange={setDuration}
            suffix="s"
          />
          <MagnificSlider
            label="Motion"
            helper="How much the subject + camera move."
            min={0}
            max={100}
            value={motion}
            onChange={setMotion}
            suffix="%"
          />
        </>
      }
    />
  );
}
