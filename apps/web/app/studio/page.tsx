"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { listGenerations, type Generation } from "@/lib/api";

const QUICK_LINKS: { label: string; href: string; glyph: string; desc: string }[] = [
  {
    label: "Image",
    href: "/studio/image",
    glyph: "▢",
    desc: "Text-to-image with Flux, Ideogram, Midjourney, Runway, Nano Banana.",
  },
  {
    label: "Video",
    href: "/studio/video",
    glyph: "▷",
    desc: "Text-to-video with Runway, Veo, Kling, Higgsfield, Sora.",
  },
  {
    label: "Edit",
    href: "/studio/edit",
    glyph: "✎",
    desc: "Paint a mask, regenerate inside it. Inpaint + fill.",
  },
  {
    label: "Enhance",
    href: "/studio/enhance",
    glyph: "✦",
    desc: "4× upscale any image or video.",
  },
  {
    label: "Lipsync",
    href: "/studio/lipsync",
    glyph: "♪",
    desc: "Drive any face from a voice track.",
  },
  {
    label: "Marketing",
    href: "/studio/marketing",
    glyph: "◎",
    desc: "Assemble Library assets into finished ads, reformat, schedule.",
  },
];

export default function StudioHome() {
  const [recent, setRecent] = useState<Generation[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const rows = await listGenerations({ limit: 12 });
        setRecent(rows);
      } catch {
        // unauth or new account — no recent yet
      }
    })();
  }, []);

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-10">
      <header className="mb-8">
        <h1 className="font-serif text-[36px] leading-none tracking-tightest text-ink">
          Creative Studio
        </h1>
        <p className="mt-2 text-[14px] text-ink-2 max-w-[60ch]">
          One canvas, every tool. Pick a modality, pick a model, ship.
          Failed generations never cost credits.
        </p>
      </header>

      <section className="mb-10">
        <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-3">
          Start a new piece
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {QUICK_LINKS.map((q) => (
            <Link
              key={q.href}
              href={q.href}
              className="group rounded-sm border border-rule bg-paper-2 p-4 hover:border-ink hover:bg-paper transition-colors"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span
                  className="inline-flex h-7 w-7 items-center justify-center rounded-sm bg-paper border border-rule text-terracotta group-hover:border-terracotta"
                  aria-hidden
                >
                  {q.glyph}
                </span>
                <div className="font-medium text-[14px] text-ink">{q.label}</div>
              </div>
              <p className="text-[12px] text-ink-2 leading-relaxed">{q.desc}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="mb-10">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
            Recent generations
          </div>
          <Link
            href="/studio/library/assets"
            className="text-[12px] text-terracotta hover:text-terracotta-2"
          >
            Library →
          </Link>
        </div>
        {recent.length === 0 ? (
          <p className="rounded-sm border border-rule bg-paper-2 p-5 text-center text-[13px] text-ink-3">
            You haven&rsquo;t generated anything yet. Start with{" "}
            <Link href="/studio/image" className="text-terracotta hover:text-terracotta-2">
              Image
            </Link>
            .
          </p>
        ) : (
          <div className="grid grid-cols-4 md:grid-cols-6 gap-2">
            {recent.map((g) => (
              <Link
                key={g.id}
                href={`/studio/${g.tool}?gen=${g.id}`}
                className="group rounded-sm border border-rule bg-paper-2 overflow-hidden hover:border-ink"
              >
                <div
                  className={cn(
                    "grid place-items-center bg-sand",
                    g.tool === "video" || g.tool === "lipsync"
                      ? "aspect-[9/16]"
                      : "aspect-square",
                  )}
                >
                  {g.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={g.thumbnail_url}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="text-[10px] text-ink-3">
                      {g.status}
                    </span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
