"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import { listRenders, type RenderJob } from "@/lib/api";

// Floating picker that shows a grid of recent completed renders and
// hands the clicked render's output_url back to the parent. Used by the
// Storefront admin to attach Creative-Studio output as a product image
// without the "copy URL, paste URL" dance.

interface Props {
  open: boolean;
  onClose: () => void;
  onPick: (url: string) => void;
  // Filter to image renders only by default — product catalogs show
  // still images, not video. Flip `allowVideo` once the storefront
  // supports <video> tiles.
  allowVideo?: boolean;
  businessId?: string;
}

export function RenderPicker({
  open,
  onClose,
  onPick,
  allowVideo = false,
  businessId,
}: Props) {
  const [renders, setRenders] = useState<RenderJob[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const rows = await listRenders({ businessId, limit: 50 });
      const completed = rows.filter(
        (r) =>
          r.status === "completed" &&
          !!r.output_url &&
          (allowVideo || r.mode === "image"),
      );
      setRenders(completed);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [allowVideo, businessId]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[70] bg-ink/40 backdrop-blur-sm grid place-items-center p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="bg-paper rounded-xl border border-rule shadow-lg w-full max-w-4xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-5 py-4 border-b border-rule">
          <div className="h-8 w-8 grid place-items-center rounded-md bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-base leading-none">
            M
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold">Attach from Creative Studio</div>
            <div className="text-[11.5px] text-ink-3">
              Pick a completed render. We&apos;ll copy its URL into this product&apos;s images.
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-7 w-7 grid place-items-center rounded-sm text-ink-3 hover:bg-sand hover:text-ink"
            aria-label="Close"
          >
            <Icon name="close" size={12} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {error && (
            <div className="rounded-md border border-rose-2/50 bg-rose-soft/50 p-3 text-sm text-rose-2 mb-4">
              {error}
            </div>
          )}

          {renders === null ? (
            <p className="text-sm text-ink-3">Loading renders…</p>
          ) : renders.length === 0 ? (
            <div className="rounded-md border border-rule bg-paper-2 p-6 text-sm text-ink-3">
              No completed{allowVideo ? "" : " image"} renders yet. Generate one in{" "}
              <span className="text-terracotta-2">Creative Studio</span> and come back.
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {renders.map((r) => (
                <RenderTile
                  key={r.id}
                  render={r}
                  onPick={() => {
                    if (r.output_url) {
                      onPick(r.output_url);
                      onClose();
                    }
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RenderTile({
  render,
  onPick,
}: {
  render: RenderJob;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      className={cn(
        "group relative aspect-square rounded-sm border border-rule overflow-hidden",
        "hover:border-terracotta transition-colors",
      )}
      title={render.prompt}
    >
      {render.mode === "video" ? (
        <video
          src={render.output_url ?? undefined}
          className="w-full h-full object-cover"
          muted
          playsInline
          preload="metadata"
          poster={render.thumbnail_url ?? undefined}
        />
      ) : (
        <img
          src={render.output_url ?? ""}
          alt={render.prompt}
          className="w-full h-full object-cover"
        />
      )}
      <div className="absolute inset-x-0 bottom-0 px-2 py-1.5 bg-gradient-to-t from-ink/75 to-transparent">
        <div className="text-[10px] text-paper/90 uppercase tracking-[0.06em] truncate">
          {render.provider}
        </div>
      </div>
      <div className="absolute inset-0 grid place-items-center bg-ink/30 opacity-0 group-hover:opacity-100 transition-opacity">
        <span className="px-2.5 py-1 bg-paper text-ink text-[11px] rounded-sm font-medium">
          Attach
        </span>
      </div>
    </button>
  );
}
