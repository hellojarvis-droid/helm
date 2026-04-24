"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  createCampaign,
  getBusiness,
  importExistingCreative,
  InsufficientCreditsError,
  listCampaigns,
  listLibrary,
  type BusinessDetail,
  type Campaign,
  type MasterCreative,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

const STATUS_FILTERS: { label: string; value: string | "" }[] = [
  { label: "All", value: "" },
  { label: "Ready", value: "ready" },
  { label: "Rendering", value: "rendering" },
  { label: "Failed", value: "failed" },
];

const ASPECT_FILTERS: { label: string; value: string | "" }[] = [
  { label: "All", value: "" },
  { label: "9:16", value: "9:16" },
  { label: "1:1", value: "1:1" },
  { label: "16:9", value: "16:9" },
  { label: "4:5", value: "4:5" },
];

export default function LibraryPage({ params }: PageProps) {
  const { id } = use(params);

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [rows, setRows] = useState<MasterCreative[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [aspect, setAspect] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [importing, setImporting] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [b, r, cs] = await Promise.all([
        getBusiness(id),
        listLibrary(id, {
          q: query || undefined,
          status: status || undefined,
          aspect: aspect || undefined,
        }),
        listCampaigns(id),
      ]);
      setBiz(b);
      setRows(r);
      setCampaigns(cs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHydrated(true);
    }
  }, [id, query, status, aspect]);

  useEffect(() => {
    void load();
  }, [load]);

  const grouped = useMemo(() => {
    const map: Record<string, MasterCreative[]> = {};
    for (const r of rows) {
      const c = r.campaign_id;
      (map[c] ??= []).push(r);
    }
    return map;
  }, [rows]);

  return (
    <AppShell>
      <div className="mx-auto max-w-[1100px] px-6 py-8">
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
          <span className="text-ink">Library</span>
        </div>

        <header className="mb-6 flex items-start justify-between gap-3">
          <div>
            <h1 className="font-serif text-[32px] leading-none text-ink">Library</h1>
            <p className="mt-2 text-[14px] text-ink-2">
              Every creative the specialists have produced for this business.
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => setImporting((v) => !v)}
          >
            {importing ? "Close import" : "Import existing ad"}
          </Button>
        </header>

        {importing && (
          <ImportForm
            businessId={id}
            campaigns={campaigns}
            onImported={() => {
              setImporting(false);
              void load();
            }}
            onCreateCampaign={async (name) => {
              const c = await createCampaign(id, { name });
              setCampaigns((prev) => [...prev, c]);
              return c;
            }}
          />
        )}

        {error && (
          <div className="mb-6 rounded-sm border border-terracotta/40 bg-terracotta/5 px-4 py-3 text-[13px] text-terracotta-2">
            {error}
          </div>
        )}

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[240px]">
            <Input
              placeholder="Search titles…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <FilterGroup label="Status" options={STATUS_FILTERS} value={status} onChange={setStatus} />
          <FilterGroup label="Aspect" options={ASPECT_FILTERS} value={aspect} onChange={setAspect} />
        </div>

        {!hydrated ? (
          <div className="text-center text-[13px] text-ink-3">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="rounded-sm border border-rule bg-paper-2 p-6 text-center text-[13px] text-ink-3">
            No creatives match your filters yet.{" "}
            <Link href="/studio" className="text-terracotta hover:text-terracotta-2">
              Open Studio →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {rows.map((r) => (
              <CreativeCard key={r.id} row={r} />
            ))}
          </div>
        )}

        <p className="mt-8 text-[11px] text-ink-3">
          {rows.length} creative{rows.length === 1 ? "" : "s"} across{" "}
          {Object.keys(grouped).length} campaign{Object.keys(grouped).length === 1 ? "" : "s"}.
        </p>
      </div>
    </AppShell>
  );
}

function FilterGroup({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { label: string; value: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3">{label}</div>
      <div className="flex gap-1">
        {options.map((o) => (
          <button
            key={o.value || "all"}
            type="button"
            onClick={() => onChange(o.value)}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[11px]",
              o.value === value
                ? "bg-ink text-paper border-ink"
                : "bg-paper text-ink-2 border-rule hover:bg-sand",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ImportForm({
  businessId,
  campaigns,
  onImported,
  onCreateCampaign,
}: {
  businessId: string;
  campaigns: Campaign[];
  onImported: () => void;
  onCreateCampaign: (name: string) => Promise<Campaign>;
}) {
  const [title, setTitle] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [description, setDescription] = useState("");
  const [aspect, setAspect] = useState<string>("9:16");
  const [campaignId, setCampaignId] = useState<string>(campaigns[0]?.id ?? "");
  const [newCampaignName, setNewCampaignName] = useState("");
  const [transcribe, setTranscribe] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!campaignId && campaigns[0]) setCampaignId(campaigns[0].id);
  }, [campaigns, campaignId]);

  const run = async () => {
    setErr(null);
    try {
      let cid = campaignId;
      if (!cid && newCampaignName.trim()) {
        const c = await onCreateCampaign(newCampaignName.trim());
        cid = c.id;
      }
      if (!cid) {
        setErr("Pick or create a campaign.");
        return;
      }
      if (!title.trim() || !videoUrl.trim()) {
        setErr("Title and URL are required.");
        return;
      }
      setBusy(true);
      await importExistingCreative(businessId, {
        campaign_id: cid,
        title: title.trim(),
        video_url: videoUrl.trim(),
        description: description.trim() || undefined,
        aspect_ratio: aspect,
        transcribe,
      });
      onImported();
    } catch (e) {
      if (e instanceof InsufficientCreditsError) {
        setErr(
          `Not enough credits — need $${(e.needed_cents / 100).toFixed(2)}, balance $${(e.balance_cents / 100).toFixed(2)}.`,
        );
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-6 rounded-sm border border-rule bg-paper-2 p-5">
      <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-3">
        Import existing ad
      </div>
      {err && (
        <p className="mb-3 rounded-sm border border-terracotta/40 bg-terracotta/5 px-3 py-2 text-[12px] text-terracotta-2">
          {err}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">Title</span>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Summer 2025 hero reel"
            disabled={busy}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">Video URL</span>
          <Input
            type="url"
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            placeholder="https://…"
            disabled={busy}
          />
        </label>
      </div>
      <label className="mt-3 block space-y-1">
        <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">
          Description (optional)
        </span>
        <textarea
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={busy}
          className="flex w-full rounded-sm border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-3/80 focus-visible:outline-none focus-visible:border-ink-2"
          placeholder="What the ad is about, so Helm can tag it."
        />
      </label>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="space-y-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">Campaign</span>
          <select
            value={campaignId}
            onChange={(e) => setCampaignId(e.target.value)}
            disabled={busy}
            className="h-9 rounded-sm border border-rule bg-paper px-2 text-sm"
          >
            <option value="">— new —</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        {!campaignId && (
          <label className="space-y-1 flex-1 min-w-[200px]">
            <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">
              New campaign name
            </span>
            <Input
              value={newCampaignName}
              onChange={(e) => setNewCampaignName(e.target.value)}
              placeholder="Imports"
              disabled={busy}
            />
          </label>
        )}
        <label className="space-y-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">Aspect</span>
          <select
            value={aspect}
            onChange={(e) => setAspect(e.target.value)}
            disabled={busy}
            className="h-9 rounded-sm border border-rule bg-paper px-2 text-sm"
          >
            <option value="9:16">9:16</option>
            <option value="1:1">1:1</option>
            <option value="16:9">16:9</option>
            <option value="4:5">4:5</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-[12px] text-ink-2">
          <input
            type="checkbox"
            checked={transcribe}
            onChange={(e) => setTranscribe(e.target.checked)}
            disabled={busy}
          />
          Transcribe audio (Whisper)
        </label>
        <div className="ml-auto">
          <Button variant="accent" onClick={run} disabled={busy}>
            {busy ? "Importing…" : "Import"}
          </Button>
        </div>
      </div>
    </section>
  );
}

function CreativeCard({ row }: { row: MasterCreative }) {
  const tone =
    row.status === "ready"
      ? "bg-sage"
      : row.status === "failed"
        ? "bg-terracotta"
        : row.status === "rendering" || row.status === "drafting"
          ? "bg-amber"
          : "bg-sand-2";
  const href = `/studio?creative=${row.id}`;
  return (
    <Link
      href={href}
      className="group rounded-sm border border-rule bg-paper-2 p-3 hover:border-ink transition-colors"
    >
      <div className="aspect-[9/16] mb-2 rounded-sm bg-sand overflow-hidden grid place-items-center">
        {row.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={row.thumbnail_url}
            alt=""
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-[11px] text-ink-3">no preview</span>
        )}
      </div>
      <div className="flex items-center gap-1.5 mb-1 text-[11px] text-ink-3">
        <span className={cn("inline-block h-1.5 w-1.5 rounded-full", tone)} />
        {row.status}
        <span className="text-ink-3/60">· {row.canonical_aspect}</span>
      </div>
      <div className="text-[13px] font-medium text-ink group-hover:text-terracotta transition-colors line-clamp-2">
        {row.title}
      </div>
      {row.copy?.copy?.headline && (
        <p className="mt-1 text-[11px] text-ink-2 line-clamp-2">
          {row.copy.copy.headline}
        </p>
      )}
    </Link>
  );
}
