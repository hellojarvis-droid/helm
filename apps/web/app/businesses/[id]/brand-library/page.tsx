"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  getBrandLibrary,
  getBusiness,
  InsufficientCreditsError,
  scrapeBrandFromUrl,
  upsertBrandLibrary,
  type BrandLibrary,
  type BusinessDetail,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

interface FormState {
  name: string;
  tagline: string;
  source_url: string;
  palette: { primary: string; secondary: string; accent: string; neutral: string };
  typography: { display: string; body: string };
  voice_paragraph: string;
  banned_phrases: string;
  moodboard_urls: string;
}

const emptyForm: FormState = {
  name: "",
  tagline: "",
  source_url: "",
  palette: { primary: "", secondary: "", accent: "", neutral: "" },
  typography: { display: "", body: "" },
  voice_paragraph: "",
  banned_phrases: "",
  moodboard_urls: "",
};

function formFromLibrary(lib: BrandLibrary): FormState {
  const palette = lib.palette as Partial<FormState["palette"]>;
  const typography = lib.typography as Partial<FormState["typography"]>;
  return {
    name: lib.name ?? "",
    tagline: lib.tagline ?? "",
    source_url: lib.source_url ?? "",
    palette: {
      primary: palette?.primary ?? "",
      secondary: palette?.secondary ?? "",
      accent: palette?.accent ?? "",
      neutral: palette?.neutral ?? "",
    },
    typography: {
      display: typography?.display ?? "",
      body: typography?.body ?? "",
    },
    voice_paragraph: lib.voice_paragraph ?? "",
    banned_phrases: (lib.banned_phrases ?? []).join(", "),
    moodboard_urls: (lib.moodboard_urls ?? []).join("\n"),
  };
}

export default function BrandLibraryPage({ params }: PageProps) {
  const { id } = use(params);

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [scraping, setScraping] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [bizRow, lib] = await Promise.all([
        getBusiness(id),
        getBrandLibrary(id),
      ]);
      setBiz(bizRow);
      if (lib) {
        setForm(formFromLibrary(lib));
        if (lib.source_url) setUrl(lib.source_url);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHydrated(true);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const onScrape = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setError(null);
    setScraping(true);
    setSaved(false);
    try {
      const { extracted } = await scrapeBrandFromUrl(id, trimmed);
      setForm((prev) => ({
        ...prev,
        name: extracted.name ?? prev.name,
        tagline: extracted.tagline ?? prev.tagline,
        source_url: trimmed,
        palette: {
          primary: extracted.palette?.primary ?? prev.palette.primary,
          secondary: extracted.palette?.secondary ?? prev.palette.secondary,
          accent: extracted.palette?.accent ?? prev.palette.accent,
          neutral: extracted.palette?.neutral ?? prev.palette.neutral,
        },
        typography: {
          display: extracted.typography?.display ?? prev.typography.display,
          body: extracted.typography?.body ?? prev.typography.body,
        },
        voice_paragraph: extracted.voice_paragraph ?? prev.voice_paragraph,
        moodboard_urls: (extracted.moodboard_keywords ?? []).length
          ? (extracted.moodboard_keywords ?? []).join("\n")
          : prev.moodboard_urls,
      }));
    } catch (e) {
      if (e instanceof InsufficientCreditsError) {
        setError(
          `Not enough credits — need ${(e.needed_cents / 100).toFixed(2)}, balance ${(e.balance_cents / 100).toFixed(2)}. Top up in the topbar.`,
        );
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setScraping(false);
    }
  };

  const onSave = async () => {
    setError(null);
    setSaved(false);
    if (!form.name.trim()) {
      setError("Brand name is required.");
      return;
    }
    setSaving(true);
    try {
      const body = {
        name: form.name.trim(),
        tagline: form.tagline.trim() || null,
        source_url: form.source_url.trim() || null,
        palette: form.palette,
        typography: form.typography,
        voice_paragraph: form.voice_paragraph.trim() || null,
        banned_phrases: form.banned_phrases
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        moodboard_urls: form.moodboard_urls
          .split(/\r?\n/)
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const saved = await upsertBrandLibrary(id, body);
      setForm(formFromLibrary(saved));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-[880px] px-6 py-8">
        <div className="mb-6 flex items-center gap-2 text-xs text-ink-3">
          <Link href="/businesses" className="hover:text-ink">
            Businesses
          </Link>
          <span aria-hidden>›</span>
          {biz ? (
            <Link href={`/businesses/${id}`} className="hover:text-ink">
              {biz.name}
            </Link>
          ) : (
            <span>—</span>
          )}
          <span aria-hidden>›</span>
          <span className="text-ink">Brand Library</span>
        </div>

        <header className="mb-8">
          <h1 className="font-serif text-[32px] leading-none text-ink">Brand Library</h1>
          <p className="mt-2 max-w-[60ch] text-[14px] leading-relaxed text-ink-2">
            Every specialist pulls from this. Palette + typography feed the Art
            Director, voice + banned phrases feed the Copywriter, logos feed the
            Editor. Paste your existing site to pre-fill, then review.
          </p>
        </header>

        {error && (
          <div className="mb-6 rounded-sm border border-terracotta/40 bg-terracotta/5 px-4 py-3 text-[13px] text-terracotta-2">
            {error}
          </div>
        )}
        {saved && (
          <div className="mb-6 rounded-sm border border-sage/50 bg-sage/10 px-4 py-3 text-[13px] text-ink">
            Saved. Specialists will read from this on their next run.
          </div>
        )}

        {/* URL-in scrape */}
        <section className="mb-8 rounded-sm border border-rule bg-paper-2 p-5">
          <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-[0.08em] text-ink-3">
            <Icon name="sparkle" className="h-3.5 w-3.5" />
            URL-in onboarding
          </div>
          <p className="mb-3 text-[13px] text-ink-2">
            Paste any page that represents your brand. Claude extracts the
            palette, typography, voice, and moodboard cues. Costs about 5¢.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              type="url"
              placeholder="https://yourbrand.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={scraping}
            />
            <Button
              variant="accent"
              onClick={onScrape}
              disabled={!url.trim() || scraping}
            >
              {scraping ? "Extracting…" : "Extract"}
            </Button>
          </div>
        </section>

        {!hydrated ? (
          <div className="text-center text-[13px] text-ink-3">Loading…</div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void onSave();
            }}
            className="space-y-8"
          >
            {/* Identity */}
            <fieldset className="space-y-4">
              <legend className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
                Identity
              </legend>
              <Field label="Brand name" required>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Pebble &amp; Bloom"
                />
              </Field>
              <Field label="Tagline">
                <Input
                  value={form.tagline}
                  onChange={(e) => setForm({ ...form, tagline: e.target.value })}
                  placeholder="One-sentence promise."
                />
              </Field>
              <Field label="Source URL">
                <Input
                  type="url"
                  value={form.source_url}
                  onChange={(e) => setForm({ ...form, source_url: e.target.value })}
                  placeholder="https://…"
                />
              </Field>
            </fieldset>

            {/* Palette */}
            <fieldset className="space-y-4">
              <legend className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
                Palette
              </legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {(["primary", "secondary", "accent", "neutral"] as const).map((k) => (
                  <Field key={k} label={k.charAt(0).toUpperCase() + k.slice(1)}>
                    <div className="flex items-center gap-2">
                      <Swatch hex={form.palette[k]} />
                      <Input
                        value={form.palette[k]}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            palette: { ...form.palette, [k]: e.target.value },
                          })
                        }
                        placeholder="#RRGGBB"
                      />
                    </div>
                  </Field>
                ))}
              </div>
            </fieldset>

            {/* Typography */}
            <fieldset className="space-y-4">
              <legend className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
                Typography
              </legend>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Display font">
                  <Input
                    value={form.typography.display}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        typography: { ...form.typography, display: e.target.value },
                      })
                    }
                    placeholder="Instrument Serif"
                  />
                </Field>
                <Field label="Body font">
                  <Input
                    value={form.typography.body}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        typography: { ...form.typography, body: e.target.value },
                      })
                    }
                    placeholder="DM Sans"
                  />
                </Field>
              </div>
              <p className="text-[11px] text-ink-3">
                Google-Fonts-available names only. Custom-licensed faces (Gotham,
                Helvetica Neue) should use a close Google equivalent.
              </p>
            </fieldset>

            {/* Voice */}
            <fieldset className="space-y-4">
              <legend className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
                Voice
              </legend>
              <Field label="Voice paragraph">
                <textarea
                  rows={4}
                  className="flex w-full rounded-sm border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-3/80 focus-visible:outline-none focus-visible:border-ink-2"
                  value={form.voice_paragraph}
                  onChange={(e) =>
                    setForm({ ...form, voice_paragraph: e.target.value })
                  }
                  placeholder="Direct, warm, no jargon. Short sentences. 5th-grade reading level."
                />
              </Field>
              <Field label="Banned phrases (comma-separated)">
                <Input
                  value={form.banned_phrases}
                  onChange={(e) =>
                    setForm({ ...form, banned_phrases: e.target.value })
                  }
                  placeholder="revolutionary, game-changer, synergy"
                />
              </Field>
            </fieldset>

            {/* Moodboard */}
            <fieldset className="space-y-4">
              <legend className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
                Moodboard
              </legend>
              <Field label="Reference URLs (one per line)">
                <textarea
                  rows={4}
                  className="flex w-full rounded-sm border border-rule bg-paper px-3 py-2 text-sm font-mono text-ink placeholder:text-ink-3/80 focus-visible:outline-none focus-visible:border-ink-2"
                  value={form.moodboard_urls}
                  onChange={(e) =>
                    setForm({ ...form, moodboard_urls: e.target.value })
                  }
                  placeholder={"https://…\nhttps://…"}
                />
              </Field>
            </fieldset>

            <div className="flex items-center justify-end gap-3 border-t border-rule pt-5">
              <Link href={`/businesses/${id}`} className="text-[13px] text-ink-3 hover:text-ink">
                Cancel
              </Link>
              <Button type="submit" disabled={saving || !form.name.trim()}>
                {saving ? "Saving…" : "Save brand library"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </AppShell>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] text-ink-2">
        {label}
        {required && <span className="ml-1 text-terracotta">*</span>}
      </span>
      {children}
    </label>
  );
}

function Swatch({ hex }: { hex: string }) {
  const valid = /^#?[0-9a-f]{6}$/i.test(hex.trim());
  const normalized = hex.trim().startsWith("#") ? hex.trim() : `#${hex.trim()}`;
  return (
    <div
      className={cn(
        "h-9 w-9 shrink-0 rounded-sm border border-rule",
        !valid && "bg-sand",
      )}
      style={valid ? { backgroundColor: normalized } : undefined}
      aria-hidden
    />
  );
}
