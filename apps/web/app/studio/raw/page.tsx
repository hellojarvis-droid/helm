"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  cancelRender,
  estimateRenderCost,
  getConnectorCatalog,
  listAccountConnections,
  listBusinesses,
  listRenders,
  startRender,
  streamRenders,
  type Business,
  type ConnectionStatus,
  type ConnectorInfo,
  type RenderJob,
} from "@/lib/api";

const MODE_CHOICES: ("image" | "video")[] = ["video", "image"];
const DEFAULT_DURATION = 5;
const DEFAULT_RATIO = "16:9";
const DEFAULT_RATIO_IMAGE = "1:1";

export default function StudioPage() {
  const [catalog, setCatalog] = useState<ConnectorInfo[]>([]);
  const [connections, setConnections] = useState<ConnectionStatus[]>([]);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [renders, setRenders] = useState<RenderJob[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scopedBizId, setScopedBizId] = useState<string | undefined>(undefined);
  // Gate: empty state should only render once we've confirmed with the API
  // that no creative provider is connected. Before the fetch lands, both
  // `catalog` and `connections` are empty and the "nothing connected"
  // predicate is trivially true — which caused the empty state to flash
  // for a moment on every load.
  const [hydrated, setHydrated] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const loadStatic = useCallback(async () => {
    setError(null);
    try {
      const [cat, conns, biz] = await Promise.all([
        getConnectorCatalog(),
        listAccountConnections(),
        listBusinesses().catch(() => [] as Business[]),
      ]);
      setCatalog(cat);
      setConnections(conns);
      setBusinesses(biz);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHydrated(true);
    }
  }, []);

  const loadRenders = useCallback(async () => {
    try {
      const rows = await listRenders({ businessId: scopedBizId, limit: 50 });
      setRenders(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [scopedBizId]);

  useEffect(() => {
    void loadStatic();
  }, [loadStatic]);

  useEffect(() => {
    void loadRenders();
  }, [loadRenders]);

  useEffect(() => {
    const ac = new AbortController();
    abortRef.current = ac;
    (async () => {
      try {
        for await (const ev of streamRenders({ businessId: scopedBizId, signal: ac.signal })) {
          if (ev.kind === "snapshot") {
            setRenders(ev.renders);
          } else if (ev.kind === "renders") {
            setRenders((prev) => {
              if (!prev) return ev.renders;
              // Merge by id; new rows prepend, existing rows update in place.
              const map = new Map(prev.map((r) => [r.id, r]));
              for (const r of ev.renders) map.set(r.id, r);
              return [...map.values()].sort((a, b) =>
                b.created_at.localeCompare(a.created_at),
              );
            });
          }
        }
      } catch (e) {
        if (!ac.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => ac.abort();
  }, [scopedBizId]);

  const creativeConnectors = useMemo(
    () =>
      catalog
        .filter((c) => c.category === "Creative" && c.auth_mode === "api_key")
        .sort((a, b) => a.popularity - b.popularity),
    [catalog],
  );
  const connectedCreativeSlugs = useMemo(
    () =>
      new Set(
        connections
          .filter(
            (c) =>
              c.status === "active" &&
              creativeConnectors.some((cc) => cc.slug === c.toolkit),
          )
          .map((c) => c.toolkit),
      ),
    [connections, creativeConnectors],
  );

  async function handleSubmit(req: {
    provider: string;
    mode: "image" | "video";
    prompt: string;
    options: Record<string, unknown>;
  }) {
    setError(null);
    try {
      const row = await startRender({
        provider: req.provider,
        mode: req.mode,
        prompt: req.prompt,
        options: req.options,
        business_id: scopedBizId,
      });
      setRenders((prev) => (prev ? [row, ...prev.filter((r) => r.id !== row.id)] : [row]));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleCancel(id: string) {
    try {
      const updated = await cancelRender(id);
      setRenders((prev) => prev?.map((r) => (r.id === id ? updated : r)) ?? prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <AppShell breadcrumbs={["Helm", "Creative Studio"]}>
      <div className="px-10 pt-8 pb-20 max-w-6xl">
        <header className="mb-7 flex items-end justify-between">
          <div>
            <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
              Creative Studio
            </h1>
            <p className="text-sm text-ink-3 max-w-prose">
              Brief Muse, pick a provider, ship the render. Uses whichever Creative-provider
              key you&apos;ve connected — your {connectedProviderCount(connections, creativeConnectors)}{" "}
              connected account
              {connectedProviderCount(connections, creativeConnectors) === 1 ? "" : "s"} billed
              directly by the provider. We show cost estimates before you submit.
            </p>
          </div>

          {businesses.length > 0 && (
            <select
              value={scopedBizId ?? ""}
              onChange={(e) => setScopedBizId(e.target.value || undefined)}
              className="h-9 rounded-sm border border-rule bg-paper px-3 text-[13px] text-ink-2"
            >
              <option value="">All businesses</option>
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          )}
        </header>

        {error && (
          <div className="mb-5 rounded-md border border-rose-2/50 bg-rose-soft/50 p-4 text-sm text-rose-2">
            {error}
          </div>
        )}

        {!hydrated ? (
          <p className="text-sm text-ink-3">Loading Studio…</p>
        ) : connectedCreativeSlugs.size === 0 ? (
          <EmptyConnectorsState creativeConnectors={creativeConnectors} />
        ) : (
          <div className="grid grid-cols-12 gap-6">
            <section className="col-span-8">
              <SectionHeader
                title="Render queue"
                note={
                  renders === null
                    ? "Loading…"
                    : `${renders.length} render${renders.length === 1 ? "" : "s"}`
                }
              />
              {renders === null ? (
                <p className="text-sm text-ink-3">Loading…</p>
              ) : renders.length === 0 ? (
                <p className="text-sm text-ink-3 p-8 rounded-md border border-rule bg-paper">
                  Nothing rendered yet. Brief Muse on the right to fire your first one.
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {renders.map((r) => (
                    <RenderTile key={r.id} render={r} onCancel={handleCancel} />
                  ))}
                </div>
              )}
            </section>

            <aside className="col-span-4">
              <BriefMuse
                connectors={creativeConnectors}
                connectedSlugs={connectedCreativeSlugs}
                onSubmit={handleSubmit}
              />
            </aside>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function connectedProviderCount(
  connections: ConnectionStatus[],
  creative: ConnectorInfo[],
): number {
  const creativeSlugs = new Set(creative.map((c) => c.slug));
  return connections.filter(
    (c) => c.status === "active" && creativeSlugs.has(c.toolkit),
  ).length;
}

function EmptyConnectorsState({
  creativeConnectors,
}: {
  creativeConnectors: ConnectorInfo[];
}) {
  return (
    <div className="rounded-md border border-rule bg-paper p-10 max-w-3xl">
      <div className="font-serif text-[32px] leading-tight tracking-tightest mb-2">
        Connect a creative provider to start.
      </div>
      <p className="text-sm text-ink-2 leading-relaxed mb-6 max-w-prose">
        Creative Studio is <strong>bring-your-own-keys</strong> — paste your Runway,
        Higgsfield, Kling, or Nano-Banana key once and Muse can use it across every business
        you run. Your provider account is billed directly; we just orchestrate and show
        estimated cost per render.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
        {creativeConnectors.slice(0, 4).map((c) => (
          <div
            key={c.slug}
            className="flex items-center gap-3 p-3 rounded-sm border border-rule bg-paper-2"
          >
            <div className="h-9 w-9 grid place-items-center rounded-md bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-base">
              {c.name[0]}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium">{c.name}</div>
              <div className="text-[11px] text-ink-3 truncate">{c.cost_hint || c.description}</div>
            </div>
          </div>
        ))}
      </div>
      <Link
        href="/connections"
        className="inline-flex items-center gap-1.5 px-4 h-11 rounded-sm bg-ink border border-ink text-paper hover:bg-terracotta hover:border-terracotta text-sm font-medium"
      >
        <Icon name="plus" size={13} /> Open Connections
      </Link>
    </div>
  );
}

function SectionHeader({ title, note }: { title: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between mb-3">
      <h2 className="text-[13px] font-medium text-ink-2 uppercase tracking-[0.08em]">
        {title}
      </h2>
      {note && <span className="text-[11px] text-ink-3">{note}</span>}
    </div>
  );
}

function RenderTile({
  render,
  onCancel,
}: {
  render: RenderJob;
  onCancel: (id: string) => void;
}) {
  const running = render.status === "running" || render.status === "queued" || render.status === "pending";
  const done = render.status === "completed";
  const failed = render.status === "failed";
  return (
    <div
      className={cn(
        "rounded-md border p-4 bg-paper flex flex-col gap-3",
        running
          ? "border-terracotta/40"
          : done
            ? "border-sage/40"
            : failed
              ? "border-rose-2/40"
              : "border-rule",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="chip">{render.provider}</span>
          <span
            className={cn(
              "chip",
              done ? "chip-sage" : running ? "chip-amber" : failed ? "chip-rose" : "",
            )}
          >
            {render.status}
          </span>
          <span className="text-[11px] text-ink-3 uppercase tracking-[0.06em]">
            {render.mode}
          </span>
        </div>
        <span className="text-[11px] font-mono text-ink-3">
          ~${(render.cost_cents_estimate / 100).toFixed(2)}
        </span>
      </div>

      <div className="aspect-video rounded-sm overflow-hidden bg-sand border border-rule grid place-items-center">
        {done && render.output_url ? (
          render.mode === "video" ? (
            <video
              className="w-full h-full object-cover"
              src={render.output_url}
              controls
              playsInline
              preload="metadata"
              poster={render.thumbnail_url ?? undefined}
            />
          ) : (
            <img
              className="w-full h-full object-cover"
              src={render.output_url}
              alt={render.prompt}
            />
          )
        ) : failed ? (
          <div className="p-4 text-[12px] text-rose-2 font-mono line-clamp-4 text-center">
            {render.error || "Render failed."}
          </div>
        ) : (
          <div className="p-4 text-[11px] text-ink-3 text-center tracking-[0.06em] uppercase">
            <span className="typing">
              <span>.</span>
              <span>.</span>
              <span>.</span>
            </span>
            {" "}
            {render.status === "queued" ? "queued" : "rendering"}
          </div>
        )}
      </div>

      <p className="text-[12.5px] text-ink-2 leading-snug line-clamp-3">{render.prompt}</p>

      <div className="flex items-center justify-between pt-2 border-t border-rule text-[11px] text-ink-3">
        <span>{new Date(render.created_at).toLocaleString()}</span>
        {running ? (
          <button
            type="button"
            className="text-ink-3 hover:text-rose-2"
            onClick={() => onCancel(render.id)}
          >
            Cancel
          </button>
        ) : done && render.output_url ? (
          <a
            className="text-terracotta-2 hover:underline"
            href={render.output_url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Open full size ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}

function BriefMuse({
  connectors,
  connectedSlugs,
  onSubmit,
}: {
  connectors: ConnectorInfo[];
  connectedSlugs: Set<string>;
  onSubmit: (req: {
    provider: string;
    mode: "image" | "video";
    prompt: string;
    options: Record<string, unknown>;
  }) => Promise<void>;
}) {
  const [mode, setMode] = useState<"image" | "video">("video");
  const [prompt, setPrompt] = useState(
    "A warm, sunlit cinematic shot of a candle burning on a wooden table, soft shallow depth of field.",
  );
  const [provider, setProvider] = useState<string>(() => {
    const connected = connectors.find(
      (c) => connectedSlugs.has(c.slug) && (mode === "image" ? true : true),
    );
    return connected?.slug ?? connectors[0]?.slug ?? "runway";
  });
  const [duration, setDuration] = useState(DEFAULT_DURATION);
  const [ratio, setRatio] = useState(DEFAULT_RATIO);
  const [estimate, setEstimate] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

  const activeConnector = connectors.find((c) => c.slug === provider);
  const isSupportedForMode = Boolean(activeConnector);
  const options: Record<string, unknown> = useMemo(() => {
    if (mode === "image") return { ratio };
    return { duration, ratio };
  }, [mode, duration, ratio]);

  // Fetch cost estimate from server so it's never out of sync with the
  // adapter. Debounce by 200ms on each input change.
  useEffect(() => {
    if (!isSupportedForMode) {
      setEstimate(null);
      return;
    }
    const t = setTimeout(() => {
      estimateRenderCost({ provider, mode, options })
        .then((res) => setEstimate(res.cost_cents_estimate))
        .catch(() => setEstimate(null));
    }, 200);
    return () => clearTimeout(t);
  }, [provider, mode, options, isSupportedForMode]);

  async function submit() {
    if (!prompt.trim()) {
      setLocalErr("Write a prompt first.");
      return;
    }
    if (!connectedSlugs.has(provider)) {
      setLocalErr(`Connect ${activeConnector?.name ?? provider} in Connections first.`);
      return;
    }
    setSubmitting(true);
    setLocalErr(null);
    try {
      await onSubmit({ provider, mode, prompt: prompt.trim(), options });
    } finally {
      setSubmitting(false);
    }
  }

  const providersForMode = connectors.filter((c) => c);
  return (
    <div className="rounded-md border border-rule bg-paper p-5 sticky top-6">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-[13px] font-medium text-ink-2">Brief Muse</h3>
        {estimate !== null && (
          <span className="text-[11px] font-mono text-ink-3">
            ~${(estimate / 100).toFixed(2)}
          </span>
        )}
      </div>

      <div className="inline-flex gap-0.5 p-[3px] bg-sand rounded-[8px] mb-4">
        {MODE_CHOICES.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => {
              setMode(m);
              setRatio(m === "image" ? DEFAULT_RATIO_IMAGE : DEFAULT_RATIO);
            }}
            className={cn(
              "px-3 py-1.5 text-[12.5px] rounded-[6px] capitalize",
              mode === m ? "bg-paper text-ink shadow-sm" : "text-ink-3",
            )}
          >
            {m}
          </button>
        ))}
      </div>

      <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
        Prompt
      </label>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={5}
        className="mt-1.5 w-full rounded-sm border border-rule bg-paper px-3 py-2 text-[14px] leading-relaxed text-ink resize-none focus:outline-none focus:border-ink-2"
      />

      <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium mt-4 block">
        Provider
      </label>
      <select
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
        className="mt-1.5 w-full h-9 rounded-sm border border-rule bg-paper px-2.5 text-[13px] text-ink"
      >
        {providersForMode.map((c) => {
          const connected = connectedSlugs.has(c.slug);
          return (
            <option key={c.slug} value={c.slug} disabled={!connected}>
              {c.name} {connected ? "" : "· not connected"}
            </option>
          );
        })}
      </select>

      {mode === "video" && (
        <div className="grid grid-cols-2 gap-3 mt-3">
          <div>
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Duration (s)
            </label>
            <input
              type="number"
              min={3}
              max={30}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="mt-1.5 w-full h-9 rounded-sm border border-rule bg-paper px-2.5 text-[13px] text-ink"
            />
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Aspect ratio
            </label>
            <select
              value={ratio}
              onChange={(e) => setRatio(e.target.value)}
              className="mt-1.5 w-full h-9 rounded-sm border border-rule bg-paper px-2.5 text-[13px] text-ink"
            >
              <option value="16:9">16:9</option>
              <option value="9:16">9:16</option>
              <option value="1:1">1:1</option>
              <option value="4:5">4:5</option>
            </select>
          </div>
        </div>
      )}

      {mode === "image" && (
        <div className="mt-3">
          <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
            Aspect ratio
          </label>
          <select
            value={ratio}
            onChange={(e) => setRatio(e.target.value)}
            className="mt-1.5 w-full h-9 rounded-sm border border-rule bg-paper px-2.5 text-[13px] text-ink"
          >
            <option value="1:1">1:1</option>
            <option value="16:9">16:9</option>
            <option value="9:16">9:16</option>
            <option value="4:5">4:5</option>
          </select>
        </div>
      )}

      {localErr && <p className="text-[12.5px] text-rose-2 mt-3">{localErr}</p>}

      <Button
        variant="accent"
        size="lg"
        className="w-full mt-4"
        onClick={() => void submit()}
        disabled={submitting}
      >
        {submitting ? "Queuing…" : (
          <>
            <Icon name="sparkle" size={13} /> Queue render
          </>
        )}
      </Button>

      <p className="text-[11px] text-ink-3 leading-relaxed mt-3">
        Runs on your {activeConnector?.name ?? provider} account. Helm never touches your wallet —
        your key bills directly.
      </p>
    </div>
  );
}
