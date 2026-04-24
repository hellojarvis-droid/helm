"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import {
  deletePreset,
  listPresets,
  type CanvasTool,
  type PresetT,
} from "@/lib/api";

const TOOLS: CanvasTool[] = ["image", "video", "edit", "enhance", "lipsync"];

export default function PresetsLibrary() {
  const [rows, setRows] = useState<PresetT[]>([]);
  const [filter, setFilter] = useState<CanvasTool | "all">("all");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listPresets());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = filter === "all" ? rows : rows.filter((p) => p.tool === filter);

  const onDelete = async (id: string) => {
    if (!confirm("Delete this preset?")) return;
    await deletePreset(id);
    void load();
  };

  return (
    <div className="max-w-[900px] mx-auto px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[28px] leading-none text-ink">Presets</h1>
        <p className="mt-2 text-[13px] text-ink-2 max-w-[60ch]">
          Saved generation configs — the model, params, and an optional
          prompt snippet. Save presets from any GenerationCard
          (&ldquo;Save preset&rdquo; action, coming in a follow-up).
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-1.5">
        {(["all", ...TOOLS] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setFilter(t)}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[11px]",
              filter === t
                ? "bg-ink text-paper border-ink"
                : "bg-paper text-ink-2 border-rule hover:bg-sand",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="rounded-sm border border-rule bg-paper-2 p-5 text-center text-[13px] text-ink-3">
          No presets in this filter.
        </div>
      ) : (
        <ul className="rounded-sm border border-rule bg-paper divide-y divide-rule">
          {visible.map((p) => (
            <li key={p.id} className="px-4 py-3 flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-[14px] font-medium text-ink">{p.name}</div>
                <div className="mt-0.5 text-[11px] text-ink-3">
                  {p.tool} · {p.model}
                  {p.prompt_template ? ` · "${p.prompt_template.slice(0, 60)}…"` : ""}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void onDelete(p.id)}
                className="text-[11px] text-ink-3 hover:text-terracotta"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
