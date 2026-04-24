"use client";

import { cn } from "@/lib/cn";
import type { Generation, ModelEntry } from "@/lib/api";

// Every output tile — runs action chips per Runway's "Use" pattern.

export function GenerationCard({
  gen,
  model,
  onAction,
  onToggleFavorite,
}: {
  gen: Generation;
  model?: ModelEntry;
  onAction: (action: ActionKind) => void;
  onToggleFavorite: () => void;
}) {
  const aspect = aspectFromParams(gen);
  const isImage = gen.tool === "image" || gen.tool === "edit" || gen.tool === "enhance";
  const isVideo = gen.tool === "video" || gen.tool === "lipsync";

  return (
    <div className="rounded-sm border border-rule bg-paper overflow-hidden">
      <div
        className={cn(
          "w-full grid place-items-center bg-sand relative",
          aspectClass(aspect),
        )}
      >
        {gen.status === "completed" && gen.output_url ? (
          isVideo ? (
            // eslint-disable-next-line jsx-a11y/media-has-caption
            <video src={gen.output_url} controls className="h-full w-full object-contain bg-ink" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={gen.output_url}
              alt=""
              className="h-full w-full object-contain"
            />
          )
        ) : gen.status === "failed" ? (
          <div className="p-4 text-center text-[12px] text-terracotta-2">
            <div className="font-medium mb-1">Generation failed</div>
            <div className="text-[11px] text-ink-3 line-clamp-3">
              {gen.error ?? "unknown"}
            </div>
            <div className="mt-2 text-[11px] text-ink-3">
              Never charged — failed generations are free.
            </div>
          </div>
        ) : (
          <div className="p-4 text-center text-[12px] text-ink-3">
            <div className="mb-1">
              <Spinner />
            </div>
            <div>
              {gen.status === "queued" ? "Queued…" : "Rendering…"}
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={onToggleFavorite}
          className={cn(
            "absolute top-2 right-2 rounded-full bg-paper/90 border border-rule px-2 py-0.5 text-[11px]",
            gen.favorited ? "text-terracotta" : "text-ink-3 hover:text-ink",
          )}
          title="Favorite"
        >
          {gen.favorited ? "★" : "☆"}
        </button>
      </div>

      <div className="border-t border-rule p-2">
        {gen.prompt && (
          <p className="text-[11px] text-ink-2 line-clamp-2 mb-1.5">{gen.prompt}</p>
        )}
        <div className="mb-1.5 flex items-center gap-2 text-[10px] text-ink-3">
          <StatusDot status={gen.status} />
          <span>{gen.status}</span>
          {model && <span>· {model.name}</span>}
          {gen.cost_cents_actual != null && (
            <span className="ml-auto tabular">{gen.cost_cents_actual}c</span>
          )}
          {gen.cost_cents_actual == null && gen.cost_cents_reserved != null && (
            <span className="ml-auto tabular text-ink-3/70">~{gen.cost_cents_reserved}c</span>
          )}
        </div>

        {gen.status === "completed" && gen.output_url && (
          <div className="flex flex-wrap gap-1">
            {isImage && (
              <>
                <ActionChip label="Animate" onClick={() => onAction("animate")} />
                <ActionChip label="Edit" onClick={() => onAction("edit")} />
                <ActionChip label="Upscale" onClick={() => onAction("upscale")} />
              </>
            )}
            {isVideo && (
              <>
                <ActionChip label="Lipsync" onClick={() => onAction("lipsync")} />
                <ActionChip label="Upscale" onClick={() => onAction("upscale")} />
              </>
            )}
            <ActionChip label="Use as ref" onClick={() => onAction("use_as_reference")} />
          </div>
        )}
      </div>
    </div>
  );
}

export type ActionKind =
  | "animate"
  | "lipsync"
  | "edit"
  | "upscale"
  | "use_as_reference";

function ActionChip({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-rule bg-paper-2 px-2 py-0.5 text-[10px] text-ink-2 hover:bg-sand hover:text-ink"
    >
      {label}
    </button>
  );
}

function StatusDot({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "bg-sage"
      : status === "failed"
        ? "bg-terracotta"
        : status === "queued" || status === "running" || status === "pending"
          ? "bg-amber animate-pulse"
          : "bg-sand-2";
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full", tone)} />;
}

function Spinner() {
  return (
    <svg
      className="inline-block h-5 w-5 animate-spin text-ink-3"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path
        fill="currentColor"
        d="M12 2a10 10 0 0 1 10 10h-3a7 7 0 0 0-7-7V2z"
      />
    </svg>
  );
}

function aspectFromParams(gen: Generation): string {
  const ar = (gen.params as Record<string, unknown>)?.aspect_ratio;
  if (typeof ar === "string") return ar;
  return gen.tool === "video" ? "9:16" : "1:1";
}

function aspectClass(aspect: string): string {
  return (
    {
      "9:16": "aspect-[9/16]",
      "1:1": "aspect-square",
      "16:9": "aspect-video",
      "4:5": "aspect-[4/5]",
    }[aspect] ?? "aspect-square"
  );
}
