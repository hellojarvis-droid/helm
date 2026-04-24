"use client";

import { useState } from "react";
import { ToolCanvas } from "@/components/studio/ToolCanvas";
import { useGenerationSession } from "@/components/studio/useGenerationSession";
import type { ReferenceChipT } from "@/lib/api";
import { useStudio } from "../layout";

export default function StudioLipsync() {
  const { businessId } = useStudio();
  const sess = useGenerationSession({ tool: "lipsync", businessId });

  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<ReferenceChipT[]>([]);
  const [audioUrl, setAudioUrl] = useState("");

  const estimatedCredits = sess.selectedModel?.cost_credits ?? 0;
  const hasFace = refs.length > 0;
  const canGo = hasFace && audioUrl.trim().length > 0;

  const onGenerate = () => {
    if (!canGo) return;
    void sess.generate({
      prompt: prompt.trim() || "Lipsync the attached face to the supplied audio.",
      params: { audio_url: audioUrl.trim() },
      references: refs,
    });
  };

  return (
    <ToolCanvas
      title="Lipsync"
      subtitle="Drive any face from a voice track. Attach the face as a reference, paste an audio URL."
      tool="lipsync"
      promptValue={prompt}
      onPromptChange={setPrompt}
      promptPlaceholder="Optional: performance notes (eyes open, warm delivery)."
      references={refs}
      onReferencesChange={setRefs}
      models={sess.models}
      modelSlug={sess.modelSlug}
      onModelChange={sess.setModelSlug}
      estimatedCredits={estimatedCredits}
      onGenerate={onGenerate}
      generateLabel={
        !hasFace
          ? "Attach a face first"
          : !audioUrl.trim()
            ? "Paste an audio URL"
            : "Lipsync"
      }
      canGenerate={canGo}
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
            Attach a photo (role <b>Describe</b>) of the face you want
            to drive. Paste a URL to an MP3 or WAV — we&rsquo;ll host-
            uploadable audio in the next pass.
          </p>
          <div>
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
              Audio URL
            </div>
            <input
              type="url"
              value={audioUrl}
              onChange={(e) => setAudioUrl(e.target.value)}
              placeholder="https://…/voice.mp3"
              className="flex w-full rounded-sm border border-rule bg-paper px-2 py-1.5 text-[13px]"
            />
          </div>
        </>
      }
    />
  );
}
