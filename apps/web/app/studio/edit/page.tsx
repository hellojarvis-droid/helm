"use client";

import { useMemo, useState } from "react";
import { MagnificSlider } from "@/components/studio/MagnificSlider";
import { ToolCanvas } from "@/components/studio/ToolCanvas";
import { useGenerationSession } from "@/components/studio/useGenerationSession";
import type { ReferenceChipT } from "@/lib/api";
import { useStudio } from "../layout";

export default function StudioEdit() {
  const { businessId } = useStudio();
  const sess = useGenerationSession({ tool: "edit", businessId });

  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<ReferenceChipT[]>([]);
  const [adherence, setAdherence] = useState(70);

  const estimatedCredits = sess.selectedModel?.cost_credits ?? 0;
  const hasTarget = refs.some(
    (r) => r.role === "magic_fill" || r.role === "background_replace",
  );

  const onGenerate = () => {
    if (!prompt.trim() || !hasTarget) return;
    void sess.generate({
      prompt: prompt.trim(),
      params: { adherence },
      references: refs,
    });
  };

  return (
    <ToolCanvas
      title="Edit"
      subtitle="Attach an image as Magic Fill or Background — describe the change — regenerate only inside the masked region."
      tool="edit"
      promptValue={prompt}
      onPromptChange={setPrompt}
      promptPlaceholder="Replace the background with a soft gallery-white void, keep the linen chair."
      references={refs}
      onReferencesChange={setRefs}
      models={sess.models}
      modelSlug={sess.modelSlug}
      onModelChange={sess.setModelSlug}
      estimatedCredits={estimatedCredits}
      onGenerate={onGenerate}
      generateLabel={hasTarget ? "Edit" : "Attach a Magic Fill image"}
      canGenerate={prompt.trim().length > 0 && hasTarget}
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
            Attach an image with role <b>Magic Fill</b> (to paint a
            region) or <b>Background</b> (to swap behind the subject).
            Mask painting lands in the next pass — for now Edit replaces
            the whole frame using the prompt + reference.
          </p>
          <MagnificSlider
            label="Prompt adherence"
            helper="Higher = stay closer to exactly what you wrote."
            min={0}
            max={100}
            value={adherence}
            onChange={setAdherence}
            suffix="%"
          />
        </>
      }
    />
  );
}
