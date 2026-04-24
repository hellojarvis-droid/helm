"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  cancelScheduledPost,
  getCreative,
  listCreativeSchedule,
  listFormats,
  listGenerations,
  patchCreative,
  reformatCreative,
  scheduleCreative,
  type FormatRender,
  type Generation,
  type MasterCreative,
  type ReformatTarget,
  type ScheduledPost,
  type ScheduleTarget,
} from "@/lib/api";
import { useStudio } from "../../layout";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function CreativeDetail({ params }: PageProps) {
  const { id } = use(params);
  const { businessId } = useStudio();

  const [creative, setCreative] = useState<MasterCreative | null>(null);
  const [formats, setFormats] = useState<FormatRender[]>([]);
  const [schedules, setSchedules] = useState<ScheduledPost[]>([]);
  const [assets, setAssets] = useState<Generation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [c, f, s, g] = await Promise.all([
        getCreative(id),
        listFormats(id).catch(() => [] as FormatRender[]),
        listCreativeSchedule(id).catch(() => [] as ScheduledPost[]),
        businessId
          ? listGenerations({ business_id: businessId, limit: 60 })
          : Promise.resolve([] as Generation[]),
      ]);
      setCreative(c);
      setFormats(f);
      setSchedules(s);
      setAssets(g);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id, businessId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!creative) {
    return (
      <div className="max-w-[900px] mx-auto px-8 py-10">
        <Link
          href="/studio/marketing"
          className="text-[12px] text-ink-3 hover:text-ink"
        >
          ← Marketing Studio
        </Link>
        <div className="mt-4 text-[13px] text-ink-3">Loading…</div>
      </div>
    );
  }

  const copy = creative.copy?.copy ?? {};

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-8">
      <Link
        href="/studio/marketing"
        className="text-[12px] text-ink-3 hover:text-ink"
      >
        ← Marketing Studio
      </Link>

      <header className="mt-3 mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="font-serif text-[28px] leading-none text-ink">
            {creative.title}
          </h1>
          <div className="mt-1 text-[12px] text-ink-3">
            {creative.status} · {creative.canonical_aspect}
          </div>
        </div>
        {creative.canonical_output_url && (
          <a
            href={creative.canonical_output_url}
            target="_blank"
            rel="noreferrer"
            className="text-[12px] text-terracotta hover:text-terracotta-2"
          >
            Open canonical render →
          </a>
        )}
      </header>

      {error && (
        <div className="mb-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </div>
      )}

      <CopyCard
        copy={copy as Record<string, string | undefined>}
        onPatch={async (body) => {
          try {
            const next = await patchCreative(id, body);
            setCreative(next);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        }}
      />

      <AssetLibraryPicker assets={assets} />

      <ReformatPane
        creative={creative}
        formats={formats}
        onReformatted={refresh}
      />

      <SchedulePane
        creative={creative}
        schedules={schedules}
        onChanged={refresh}
      />
    </div>
  );
}

// ── Copy editor ──────────────────────────────────────────────

function CopyCard({
  copy,
  onPatch,
}: {
  copy: Record<string, string | undefined>;
  onPatch: (body: Record<string, string | undefined>) => Promise<void> | void;
}) {
  return (
    <section className="mb-6 rounded-sm border border-rule bg-paper p-4 space-y-3">
      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-3">
        Copy
      </div>
      <InlineField
        label="Headline"
        value={copy.headline ?? ""}
        onSave={(v) => onPatch({ headline: v })}
      />
      <InlineField
        label="Subhead"
        value={copy.subhead ?? ""}
        onSave={(v) => onPatch({ subhead: v })}
      />
      <InlineField
        label="CTA"
        value={copy.cta ?? ""}
        onSave={(v) => onPatch({ cta: v })}
      />
      <InlineField
        label="Caption · Meta"
        value={copy.caption_meta ?? ""}
        onSave={(v) => onPatch({ caption_meta: v })}
        multiline
      />
      <InlineField
        label="Caption · TikTok"
        value={copy.caption_tiktok ?? ""}
        onSave={(v) => onPatch({ caption_tiktok: v })}
        multiline
      />
    </section>
  );
}

function InlineField({
  label,
  value,
  onSave,
  multiline,
}: {
  label: string;
  value: string;
  onSave: (v: string) => void;
  multiline?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);

  if (!editing) {
    return (
      <div className="flex items-start gap-3">
        <div className="w-[120px] shrink-0 text-[10px] uppercase tracking-[0.06em] text-ink-3">
          {label}
        </div>
        <div className="flex-1 text-[13px] text-ink-2">
          {value || <span className="text-ink-3/70">—</span>}
        </div>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-[11px] text-terracotta hover:text-terracotta-2"
        >
          Edit
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3">
      <div className="w-[120px] shrink-0 text-[10px] uppercase tracking-[0.06em] text-ink-3">
        {label}
      </div>
      <div className="flex-1">
        {multiline ? (
          <textarea
            autoFocus
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="flex w-full rounded-sm border border-rule bg-paper px-2 py-1 text-[13px]"
          />
        ) : (
          <Input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        )}
        <div className="mt-1 flex justify-end gap-1">
          <button
            type="button"
            onClick={() => {
              setDraft(value);
              setEditing(false);
            }}
            className="rounded-sm border border-rule bg-paper px-2 py-0.5 text-[10px] hover:bg-sand"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              if (draft !== value) onSave(draft);
              setEditing(false);
            }}
            className="rounded-sm border border-ink bg-ink px-2 py-0.5 text-[10px] text-paper hover:bg-terracotta hover:border-terracotta"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Library picker — attach generations as visual assets ──────

function AssetLibraryPicker({ assets }: { assets: Generation[] }) {
  const playable = assets.filter(
    (a) =>
      a.status === "completed" &&
      a.output_url &&
      (a.tool === "video" || a.tool === "image" || a.tool === "edit" || a.tool === "enhance"),
  );

  if (playable.length === 0) {
    return (
      <section className="mb-6 rounded-sm border border-rule bg-paper-2 p-4 text-[13px] text-ink-3">
        You don&rsquo;t have any ready Library generations for this
        business yet.{" "}
        <Link href="/studio/image" className="text-terracotta hover:text-terracotta-2">
          Generate one →
        </Link>
      </section>
    );
  }

  return (
    <section className="mb-6 rounded-sm border border-rule bg-paper p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.08em] text-ink-3">
          Library assets (preview)
        </div>
        <Link
          href="/studio/library/assets"
          className="text-[11px] text-terracotta hover:text-terracotta-2"
        >
          Open Library →
        </Link>
      </div>
      <p className="mb-3 text-[11px] text-ink-3">
        Your recent ready generations. Storyboard attachment (attach N
        shots in order, mark canonical) lands in the next pass.
      </p>
      <div className="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-2">
        {playable.slice(0, 30).map((g) => (
          <a
            key={g.id}
            href={g.output_url!}
            target="_blank"
            rel="noreferrer"
            className="group rounded-sm border border-rule p-1 bg-paper-2 hover:border-ink"
          >
            <div className="aspect-square grid place-items-center bg-sand overflow-hidden rounded-sm">
              {g.thumbnail_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={g.thumbnail_url} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="text-[10px] text-ink-3">{g.status}</span>
              )}
            </div>
            <div className="mt-1 text-[10px] text-ink-3">{g.tool}</div>
          </a>
        ))}
      </div>
    </section>
  );
}

// ── Reformat pane ────────────────────────────────────────────

const PRESETS: { label: string; targets: ReformatTarget[] }[] = [
  {
    label: "Social pack (9:16 · 1:1 · 4:5)",
    targets: [
      { platform: "instagram_reels", aspect: "9:16", mode: "video" },
      { platform: "instagram", aspect: "1:1", mode: "video" },
      { platform: "facebook", aspect: "4:5", mode: "video" },
    ],
  },
  {
    label: "Vertical-first (IG · TikTok · YT Shorts)",
    targets: [
      { platform: "instagram_reels", aspect: "9:16", mode: "video" },
      { platform: "tiktok", aspect: "9:16", mode: "video" },
      { platform: "youtube_shorts", aspect: "9:16", mode: "video" },
    ],
  },
  {
    label: "Horizontal (YT · X · LinkedIn)",
    targets: [
      { platform: "youtube", aspect: "16:9", mode: "video" },
      { platform: "twitter", aspect: "16:9", mode: "video" },
      { platform: "linkedin", aspect: "16:9", mode: "video" },
    ],
  },
];

function ReformatPane({
  creative,
  formats,
  onReformatted,
}: {
  creative: MasterCreative;
  formats: FormatRender[];
  onReformatted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const canReformat = creative.status === "ready";

  const run = async (targets: ReformatTarget[]) => {
    if (!canReformat) return;
    setBusy(true);
    try {
      await reformatCreative(creative.id, targets);
      onReformatted();
    } catch {
      // noop; detail error surfaces via schedule
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-6 rounded-sm border border-rule bg-paper p-4">
      <div className="mb-3 flex items-start justify-between gap-3 border-b border-rule pb-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.08em] text-ink-3">Reformat</div>
          <div className="text-[14px] font-medium text-ink">Fan this out across formats</div>
          <div className="text-[11px] text-ink-3 mt-0.5">
            {canReformat
              ? "Pick a preset — we\u2019ll re-lay the Timeline for each target aspect."
              : "Reformat unlocks once the creative is marked ready."}
          </div>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            disabled={!canReformat || busy}
            onClick={() => void run(p.targets)}
            className={cn(
              "rounded-sm border p-3 text-left",
              canReformat && !busy
                ? "border-rule bg-paper-2 hover:border-ink hover:bg-sand"
                : "border-rule bg-paper-2 opacity-50 cursor-not-allowed",
            )}
          >
            <div className="text-[12px] font-medium text-ink">{p.label}</div>
            <div className="mt-1 text-[10px] text-ink-3">
              {p.targets.map((t) => `${t.platform} ${t.aspect}`).join(" · ")}
            </div>
          </button>
        ))}
      </div>
      {formats.length > 0 && (
        <div className="mt-5">
          <div className="text-[10px] uppercase tracking-[0.08em] text-ink-3 mb-2">
            Existing renders
          </div>
          <div className="grid grid-cols-2 gap-2">
            {formats.map((f) => (
              <div
                key={f.id}
                className="rounded-sm border border-rule bg-paper-2 p-2 text-[12px]"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">
                    {f.platform} · {f.aspect}
                  </span>
                  <span className="text-ink-3">{f.status}</span>
                </div>
                {f.output_url && (
                  <a
                    href={f.output_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-[11px] text-terracotta hover:text-terracotta-2"
                  >
                    Open →
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// ── Schedule pane ────────────────────────────────────────────

const PLATFORMS: { platform: string; aspect: ScheduleTarget["aspect"] }[] = [
  { platform: "instagram_reels", aspect: "9:16" },
  { platform: "tiktok", aspect: "9:16" },
  { platform: "youtube_shorts", aspect: "9:16" },
  { platform: "instagram", aspect: "1:1" },
  { platform: "facebook", aspect: "4:5" },
  { platform: "twitter", aspect: "16:9" },
  { platform: "linkedin", aspect: "16:9" },
];

function SchedulePane({
  creative,
  schedules,
  onChanged,
}: {
  creative: MasterCreative;
  schedules: ScheduledPost[];
  onChanged: () => void;
}) {
  const defaultWhen = (() => {
    const d = new Date();
    d.setHours(d.getHours() + 24, 0, 0, 0);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  })();
  const [when, setWhen] = useState(defaultWhen);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSchedule = creative.status === "ready";

  const run = async () => {
    if (!canSchedule) return;
    const targets = PLATFORMS.filter((p) => selected[`${p.platform}:${p.aspect}`]).map(
      (p) => ({ platform: p.platform, aspect: p.aspect }) as ScheduleTarget,
    );
    if (targets.length === 0) {
      setError("Pick at least one platform.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await scheduleCreative(creative.id, {
        scheduled_at: new Date(when).toISOString(),
        targets,
      });
      setSelected({});
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onCancel = async (id: string) => {
    try {
      await cancelScheduledPost(id);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section className="mb-6 rounded-sm border border-rule bg-paper p-4">
      <div className="mb-3 flex items-start justify-between gap-3 border-b border-rule pb-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.08em] text-ink-3">Schedule</div>
          <div className="text-[14px] font-medium text-ink">
            Publish to connected platforms
          </div>
          <div className="text-[11px] text-ink-3 mt-0.5">
            {canSchedule
              ? "Pick a date/time and platforms. Cancel any time before publish."
              : "Scheduling unlocks once the creative is ready."}
          </div>
        </div>
      </div>

      {error && (
        <p className="mb-3 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {error}
        </p>
      )}

      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3">When</div>
          <input
            type="datetime-local"
            value={when}
            onChange={(e) => setWhen(e.target.value)}
            disabled={!canSchedule || busy}
            className="h-9 rounded-sm border border-rule bg-paper px-2 text-sm"
          />
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
            Platforms
          </div>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
            {PLATFORMS.map((p) => {
              const key = `${p.platform}:${p.aspect}`;
              const on = !!selected[key];
              return (
                <button
                  key={key}
                  type="button"
                  disabled={!canSchedule || busy}
                  onClick={() => setSelected((prev) => ({ ...prev, [key]: !prev[key] }))}
                  className={cn(
                    "rounded-sm border px-2.5 py-1.5 text-[11px]",
                    on
                      ? "bg-ink text-paper border-ink"
                      : "bg-paper text-ink-2 border-rule hover:bg-sand",
                    !canSchedule && "opacity-50 cursor-not-allowed",
                  )}
                >
                  {p.platform}
                  <span className="ml-1 text-ink-3/80">{p.aspect}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex justify-end">
          <Button variant="accent" onClick={run} disabled={!canSchedule || busy}>
            {busy ? "Scheduling…" : "Schedule"}
          </Button>
        </div>
      </div>

      {schedules.length > 0 && (
        <div className="mt-5 border-t border-rule pt-4">
          <div className="text-[10px] uppercase tracking-[0.08em] text-ink-3 mb-2">
            Upcoming &amp; past
          </div>
          <ul className="space-y-1.5">
            {schedules.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between rounded-sm border border-rule bg-paper-2 px-3 py-2 text-[12px]"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{s.platform}</span>
                    <span className="text-ink-3">{s.aspect}</span>
                    <span className="text-ink-3">· {s.status}</span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-ink-3">
                    {new Date(s.scheduled_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {s.external_post_url && (
                    <a
                      href={s.external_post_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-terracotta hover:text-terracotta-2"
                    >
                      View →
                    </a>
                  )}
                  {s.status === "scheduled" && (
                    <button
                      type="button"
                      onClick={() => void onCancel(s.id)}
                      className="text-[11px] text-ink-3 hover:text-terracotta"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
