"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  createCharacter,
  deleteCharacter,
  listCharacters,
  type CharacterT,
} from "@/lib/api";
import { useStudio } from "../../layout";

export default function CharactersLibrary() {
  const { businessId, businesses } = useStudio();
  const [rows, setRows] = useState<CharacterT[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [urls, setUrls] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setError(null);
    try {
      setRows(await listCharacters(businessId));
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
    if (!businessId || !name.trim() || urls.length === 0) return;
    setBusy(true);
    try {
      await createCharacter(businessId, {
        name: name.trim(),
        reference_image_urls: urls,
      });
      setName("");
      setUrls([]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm("Delete this character?")) return;
    try {
      await deleteCharacter(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-[28px] leading-none text-ink">Characters</h1>
          <p className="mt-2 text-[13px] text-ink-2 max-w-[60ch]">
            First-class trained identities. Upload 4–8 reference photos,
            name the character, then attach it as a Character reference
            on any Image or Video generation.
          </p>
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </div>
      )}

      {!businessId && (
        <div className="rounded-sm border border-rule bg-paper-2 p-4 text-[13px] text-ink-3">
          {businesses.length === 0
            ? "Create a business first."
            : "Pick a business in the left sidebar."}
        </div>
      )}

      {businessId && (
        <>
          <section className="mb-8 rounded-sm border border-rule bg-paper-2 p-5">
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-3">
              New character
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_auto]">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Nora the founder"
                disabled={busy}
              />
              <Button
                variant="outline"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
              >
                + Add photos
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                multiple
                onChange={onFiles}
                className="hidden"
              />
            </div>
            {urls.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
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
            <div className="mt-3 flex items-center justify-between">
              <p className="text-[10px] text-ink-3">
                Training wires up in the next pass. For now the character
                stores reference URLs you can attach by hand.
              </p>
              <Button
                variant="accent"
                onClick={onCreate}
                disabled={busy || !name.trim() || urls.length === 0}
              >
                Save character
              </Button>
            </div>
          </section>

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {rows.map((r) => (
              <div key={r.id} className="rounded-sm border border-rule bg-paper overflow-hidden">
                <div className="aspect-square grid place-items-center bg-sand">
                  {r.reference_image_urls[0] ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={r.reference_image_urls[0]}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="text-[10px] text-ink-3">no photo</span>
                  )}
                </div>
                <div className="p-2">
                  <div className="text-[13px] font-medium text-ink">{r.name}</div>
                  <div className="mt-0.5 flex items-center justify-between text-[10px] text-ink-3">
                    <span className={cn("rounded-full bg-sand px-1.5 py-0.5")}>
                      {r.status}
                    </span>
                    <button
                      type="button"
                      onClick={() => void onDelete(r.id)}
                      className="text-ink-3 hover:text-terracotta"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {rows.length === 0 && (
              <div className="col-span-full rounded-sm border border-rule bg-paper-2 p-5 text-center text-[13px] text-ink-3">
                No characters yet.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
