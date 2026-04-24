"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  createStyle,
  deleteStyle,
  listStyles,
  type StyleT,
} from "@/lib/api";
import { useStudio } from "../../layout";

export default function StylesLibrary() {
  const { businessId, businesses } = useStudio();
  const [rows, setRows] = useState<StyleT[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [urls, setUrls] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    try {
      setRows(await listStyles(businessId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [businessId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    const readers = files.map(
      (f) =>
        new Promise<string>((resolve) => {
          const r = new FileReader();
          r.onload = () => resolve(typeof r.result === "string" ? r.result : "");
          r.readAsDataURL(f);
        }),
    );
    const next = await Promise.all(readers);
    setUrls((prev) => [...prev, ...next.filter(Boolean)]);
    e.target.value = "";
  };

  const onCreate = async () => {
    if (!businessId || !name.trim()) return;
    setBusy(true);
    try {
      await createStyle(businessId, {
        name: name.trim(),
        reference_image_urls: urls,
        notes: notes.trim() || null,
      });
      setName("");
      setNotes("");
      setUrls([]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm("Delete this style?")) return;
    try {
      await deleteStyle(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[28px] leading-none text-ink">Styles</h1>
        <p className="mt-2 text-[13px] text-ink-2 max-w-[60ch]">
          Moodboards + style references. Attach as a Style reference to
          transfer the look to any new generation.
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </div>
      )}

      {!businessId && (
        <div className="rounded-sm border border-rule bg-paper-2 p-4 text-[13px] text-ink-3">
          {businesses.length === 0 ? "Create a business first." : "Pick a business in the left sidebar."}
        </div>
      )}

      {businessId && (
        <>
          <section className="mb-8 rounded-sm border border-rule bg-paper-2 p-5">
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-3">
              New style
            </div>
            <div className="grid gap-3">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Warm linen"
                disabled={busy}
              />
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="Prompt cues, color notes, anything to remember."
                className="flex w-full rounded-sm border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-3/80 focus-visible:outline-none focus-visible:border-ink-2"
                disabled={busy}
              />
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  onClick={() => fileRef.current?.click()}
                  disabled={busy}
                >
                  + Add moodboard images
                </Button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={onFiles}
                  className="hidden"
                />
                <Button
                  variant="accent"
                  onClick={onCreate}
                  disabled={busy || !name.trim()}
                  className="ml-auto"
                >
                  Save style
                </Button>
              </div>
              {urls.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {urls.map((u, i) => (
                    <div key={i} className="relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={u}
                        alt=""
                        className="h-16 w-16 rounded-sm object-cover border border-rule"
                      />
                      <button
                        type="button"
                        onClick={() => setUrls((prev) => prev.filter((_, j) => j !== i))}
                        className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-ink text-paper text-[10px] grid place-items-center"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {rows.map((s) => (
              <div key={s.id} className="rounded-sm border border-rule bg-paper overflow-hidden">
                <div className="aspect-square grid place-items-center bg-sand">
                  {s.reference_image_urls[0] ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={s.reference_image_urls[0]}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="text-[10px] text-ink-3">no image</span>
                  )}
                </div>
                <div className="p-2">
                  <div className="text-[13px] font-medium text-ink">{s.name}</div>
                  {s.notes && (
                    <p className="mt-0.5 text-[11px] text-ink-3 line-clamp-2">{s.notes}</p>
                  )}
                  <div className="mt-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() => void onDelete(s.id)}
                      className="text-[10px] text-ink-3 hover:text-terracotta"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {rows.length === 0 && (
              <div className="col-span-full rounded-sm border border-rule bg-paper-2 p-5 text-center text-[13px] text-ink-3">
                No styles yet.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
