"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  listGenerations,
  type CanvasTool,
  type Generation,
} from "@/lib/api";
import { useStudio } from "../../layout";

const TOOLS: CanvasTool[] = ["image", "video", "edit", "enhance", "lipsync"];

export default function AssetsLibrary() {
  const { businessId } = useStudio();
  const [rows, setRows] = useState<Generation[]>([]);
  const [q, setQ] = useState("");
  const [toolFilter, setToolFilter] = useState<CanvasTool | "all">("all");
  const [favoritedOnly, setFavoritedOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const rows = await listGenerations({
        business_id: businessId ?? undefined,
        tool: toolFilter === "all" ? undefined : toolFilter,
        favorited: favoritedOnly || undefined,
        limit: 300,
      });
      setRows(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [businessId, toolFilter, favoritedOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((r) =>
      (r.prompt || "").toLowerCase().includes(needle) ||
      r.model.toLowerCase().includes(needle) ||
      r.tool.includes(needle),
    );
  }, [rows, q]);

  return (
    <div className="max-w-[1200px] mx-auto px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[28px] leading-none text-ink">Assets</h1>
        <p className="mt-2 text-[13px] text-ink-2 max-w-[60ch]">
          Every generation across every tool. Click any to open it in
          its original canvas.
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="min-w-[220px] flex-1">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search prompts, models, tools…"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(["all", ...TOOLS] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setToolFilter(t)}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-[11px]",
                toolFilter === t
                  ? "bg-ink text-paper border-ink"
                  : "bg-paper text-ink-2 border-rule hover:bg-sand",
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-[11px] text-ink-2">
          <input
            type="checkbox"
            checked={favoritedOnly}
            onChange={(e) => setFavoritedOnly(e.target.checked)}
          />
          Favorites
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-sm border border-rule bg-paper-2 p-5 text-center text-[13px] text-ink-3">
          Nothing matches your filters.
        </div>
      ) : (
        <div className="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-2">
          {filtered.map((g) => (
            <Link
              key={g.id}
              href={`/studio/${g.tool}?session=${g.session_id}&gen=${g.id}`}
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
                  <img src={g.thumbnail_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span className="text-[10px] text-ink-3">{g.status}</span>
                )}
              </div>
              <div className="p-1.5">
                <div className="text-[10px] text-ink-3 flex items-center gap-1">
                  {g.favorited && <span className="text-terracotta">★</span>}
                  {g.tool} · {g.model}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
