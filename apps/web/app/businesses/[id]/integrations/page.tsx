"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ConnectSheet } from "@/components/connections/ConnectSheet";
import { ConnectorLogo } from "@/components/connections/ConnectorLogo";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import {
  disconnectBusinessIntegration,
  getBusiness,
  getConnectorCatalog,
  listBusinessIntegrations,
  saveBusinessApiKey,
  startBusinessOAuth,
  syncBusinessIntegration,
  type BusinessDetail,
  type BusinessIntegration,
  type ConnectorInfo,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

const CATEGORIES = ["All", "Commerce", "Ads", "Social", "Ops"] as const;
type Category = (typeof CATEGORIES)[number];
type SortKey = "popular" | "alpha";

export default function BusinessIntegrationsPage({ params }: PageProps) {
  const { id } = use(params);

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [catalog, setCatalog] = useState<ConnectorInfo[]>([]);
  const [integrations, setIntegrations] = useState<BusinessIntegration[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<Category>("All");
  const [sortKey, setSortKey] = useState<SortKey>("popular");
  const [openSlug, setOpenSlug] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [bizRow, cat, rows] = await Promise.all([
        getBusiness(id),
        getConnectorCatalog(),
        listBusinessIntegrations(id),
      ]);
      setBiz(bizRow);
      setCatalog(cat);
      setIntegrations(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHydrated(true);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const businessConnectors = useMemo(
    () => catalog.filter((c) => c.scope === "business"),
    [catalog],
  );

  const integrationByToolkit = useMemo(
    () => new Map(integrations.map((r) => [r.toolkit, r])),
    [integrations],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let items = businessConnectors;
    if (category !== "All") items = items.filter((c) => c.category === category);
    if (q) {
      items = items.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.description.toLowerCase().includes(q) ||
          c.category.toLowerCase().includes(q),
      );
    }
    return [...items].sort((a, b) =>
      sortKey === "alpha" ? a.name.localeCompare(b.name) : a.popularity - b.popularity,
    );
  }, [businessConnectors, category, search, sortKey]);

  const connectedCount = integrations.filter((r) => r.status === "active").length;
  const openConnector = catalog.find((c) => c.slug === openSlug) ?? null;
  const openIntegration = openSlug ? integrationByToolkit.get(openSlug) ?? null : null;

  async function handleDisconnect(slug: string) {
    try {
      await disconnectBusinessIntegration(id, slug);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleSync(row: BusinessIntegration) {
    try {
      await syncBusinessIntegration(row.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <AppShell breadcrumbs={["Helm", "Businesses", biz?.name ?? "Business", "Integrations"]}>
      <div className="px-10 pt-8 pb-20 max-w-5xl">
        <header className="mb-7 flex items-end justify-between">
          <div>
            <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">
              {biz?.name ?? "Business"} · integrations
            </div>
            <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
              Wire up this business
            </h1>
            <p className="text-sm text-ink-3 max-w-prose">
              Business-scoped connectors — Shopify, Meta Ads, and the rest. Account-wide tools
              (your Runway, Gmail, Notion) live on{" "}
              <Link href="/connections" className="text-terracotta-2 hover:underline">
                /connections
              </Link>
              .
            </p>
          </div>
          <div className="text-right">
            <div className="font-serif text-[36px] leading-none tracking-tightest tabular">
              {connectedCount}
            </div>
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3">connected</div>
          </div>
        </header>

        <div className="flex flex-col gap-4 mb-6">
          <div className="relative">
            <Icon
              name="search"
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"
            />
            <input
              type="search"
              placeholder="Search business-scoped connectors…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-10 pl-9 pr-3 rounded-sm border border-rule bg-paper text-[14px] text-ink placeholder:text-ink-3 focus:outline-none focus:border-ink-2"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {CATEGORIES.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCategory(c)}
                className={cn(
                  "px-3 py-1.5 rounded-full text-[12px] border transition-colors",
                  category === c
                    ? "bg-ink text-paper border-ink"
                    : "bg-paper text-ink-2 border-rule hover:bg-sand hover:text-ink",
                )}
              >
                {c}
              </button>
            ))}
            <div className="flex-1" />
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="h-8 px-3 rounded-sm border border-rule bg-paper text-[12px] text-ink-2"
            >
              <option value="popular">Sort: Most popular</option>
              <option value="alpha">Sort: A–Z</option>
            </select>
          </div>
        </div>

        {error && (
          <div className="mb-5 rounded-md border border-rose-2/50 bg-rose-soft/50 p-4 text-sm text-rose-2">
            {error}
          </div>
        )}

        {!hydrated ? (
          <p className="text-sm text-ink-3">Loading integrations…</p>
        ) : filtered.length === 0 ? (
          <div className="rounded-md border border-rule bg-paper p-8 max-w-xl">
            <div className="font-serif text-[22px] leading-tight mb-2">Nothing matches.</div>
            <p className="text-sm text-ink-3">
              Clear the search, pick a different category, or let us know what&apos;s missing.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filtered.map((c) => {
              const row = integrationByToolkit.get(c.slug) ?? null;
              return (
                <IntegrationCard
                  key={c.slug}
                  connector={c}
                  integration={row}
                  onOpen={() => setOpenSlug(c.slug)}
                  onDisconnect={() => void handleDisconnect(c.slug)}
                  onSync={() => row && void handleSync(row)}
                />
              );
            })}
          </div>
        )}

        <div className="mt-10">
          <Link href={`/businesses/${id}`} className="text-sm text-ink-3 hover:text-ink">
            ← Back to {biz?.name ?? "business"}
          </Link>
        </div>
      </div>

      {openConnector && biz && (
        <ConnectSheet
          connector={openConnector}
          connection={
            openIntegration
              ? {
                  status: openIntegration.status,
                  has_api_key: openIntegration.has_api_key,
                  masked_key: openIntegration.masked_key,
                }
              : null
          }
          scopeLabel={`${biz.name} · per-business`}
          onSaveApiKey={(slug, apiKey) => saveBusinessApiKey(id, slug, apiKey)}
          onStartOauth={(slug) => startBusinessOAuth(id, slug)}
          onClose={() => setOpenSlug(null)}
          onChanged={async () => {
            await load();
          }}
        />
      )}
    </AppShell>
  );
}

function IntegrationCard({
  connector,
  integration,
  onOpen,
  onDisconnect,
  onSync,
}: {
  connector: ConnectorInfo;
  integration: BusinessIntegration | null;
  onOpen: () => void;
  onDisconnect: () => void;
  onSync: () => void;
}) {
  const connected = integration?.status === "active";
  const pending = integration?.status === "pending";
  const failed = integration?.status === "failed" || integration?.status === "expired";

  return (
    <button
      type="button"
      onClick={onOpen}
      className="text-left rounded-md border border-rule bg-paper p-5 hover:bg-paper-2 transition-colors group"
    >
      <div className="flex items-start gap-3">
        <ConnectorLogo connector={connector} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-medium truncate">{connector.name}</span>
            {connector.popularity <= 10 && (
              <span className="text-[10px] text-ink-3 uppercase tracking-[0.06em]">
                Most popular
              </span>
            )}
            <span className="ml-auto flex items-center gap-1.5">
              {connected && <span className="chip chip-sage">connected</span>}
              {pending && <span className="chip chip-amber">pending</span>}
              {failed && <span className="chip chip-rose">{integration?.status}</span>}
              <span className="h-7 w-7 grid place-items-center rounded-sm border border-rule text-ink-3 group-hover:bg-sand group-hover:text-ink transition-colors">
                {connected ? <Icon name="settings" size={14} /> : <Icon name="plus" size={14} />}
              </span>
            </span>
          </div>
          <p className="text-[12.5px] text-ink-3 mt-1.5 leading-relaxed">{connector.description}</p>
          <div className="flex items-center gap-3 mt-2 text-[11px] text-ink-3">
            <span>{connector.category}</span>
            {connector.cost_hint && <span>· {connector.cost_hint}</span>}
            {connected && connector.auth_mode === "api_key" && integration?.masked_key && (
              <span className="font-mono">· {integration.masked_key}</span>
            )}
          </div>
        </div>
      </div>

      {(connected || pending || failed) && (
        <div
          className="flex gap-3 mt-4 pt-3 border-t border-rule text-[12px]"
          onClick={(e) => e.stopPropagation()}
        >
          {pending && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSync();
              }}
              className="text-terracotta-2 hover:underline"
            >
              Check status
            </button>
          )}
          {failed && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onOpen();
              }}
              className="text-terracotta-2 hover:underline"
            >
              Reconnect
            </button>
          )}
          {(connected || failed) && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDisconnect();
              }}
              className="text-ink-3 hover:text-rose-2 ml-auto"
            >
              Disconnect
            </button>
          )}
        </div>
      )}
    </button>
  );
}

