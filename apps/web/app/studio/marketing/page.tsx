"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  apiFetch,
  createCampaign,
  listCampaigns,
  listCreatives,
  type Campaign,
  type MasterCreative,
} from "@/lib/api";
import { useStudio } from "../layout";

// Marketing Studio is curation only. No DAG. Users pick Library
// generations, bundle into a MasterCreative, then use the existing
// reformat + schedule infra (rendered in child detail route).

export default function MarketingStudio() {
  const { businessId, businesses } = useStudio();

  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [creatives, setCreatives] = useState<MasterCreative[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newCampaign, setNewCampaign] = useState("");
  const [newCreativeTitle, setNewCreativeTitle] = useState("");
  const [aspect, setAspect] = useState<string>("9:16");

  const loadCampaigns = useCallback(async () => {
    if (!businessId) return;
    try {
      setCampaigns(await listCampaigns(businessId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [businessId]);

  const loadCreatives = useCallback(async () => {
    if (!campaignId) {
      setCreatives([]);
      return;
    }
    try {
      setCreatives(await listCreatives(campaignId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [campaignId]);

  useEffect(() => {
    void loadCampaigns();
  }, [loadCampaigns]);
  useEffect(() => {
    void loadCreatives();
  }, [loadCreatives]);

  const onCreateCampaign = async () => {
    if (!businessId || !newCampaign.trim()) return;
    try {
      const c = await createCampaign(businessId, { name: newCampaign.trim() });
      setNewCampaign("");
      setCampaignId(c.id);
      await loadCampaigns();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onCreateCreative = async () => {
    if (!campaignId || !newCreativeTitle.trim()) return;
    try {
      const res = await apiFetch(`/campaigns/${campaignId}/creatives`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          title: newCreativeTitle.trim(),
          aspect_ratio: aspect,
        }),
      });
      if (!res.ok) throw new Error(`create creative: ${res.status}`);
      setNewCreativeTitle("");
      await loadCreatives();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[32px] leading-none text-ink">Marketing Studio</h1>
        <p className="mt-2 text-[14px] text-ink-2 max-w-[65ch]">
          Bundle Library assets into finished ads, fan out to every
          aspect ratio, schedule direct-pushes across connected
          platforms. Curator only — generation happens in Image / Video /
          Edit / Enhance / Lipsync.
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
          <section className="mb-6 rounded-sm border border-rule bg-paper-2 p-5">
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-3">
              Campaigns
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {campaigns.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setCampaignId(c.id)}
                  className={cn(
                    "rounded-sm border px-3 py-1.5 text-[12px]",
                    campaignId === c.id
                      ? "border-ink bg-paper"
                      : "border-rule bg-paper hover:bg-sand",
                  )}
                >
                  {c.name}
                  <span className="ml-1 text-ink-3">· {c.status}</span>
                </button>
              ))}
              {campaigns.length === 0 && (
                <span className="text-[12px] text-ink-3">No campaigns yet.</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={newCampaign}
                onChange={(e) => setNewCampaign(e.target.value)}
                placeholder="New campaign name"
              />
              <Button variant="outline" onClick={onCreateCampaign} disabled={!newCampaign.trim()}>
                + Campaign
              </Button>
            </div>
          </section>

          {campaignId && (
            <section className="rounded-sm border border-rule bg-paper p-5">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
                  Master creatives
                </div>
                <Link
                  href="/studio/library/assets"
                  className="text-[11px] text-terracotta hover:text-terracotta-2"
                >
                  Browse Library →
                </Link>
              </div>
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Input
                  value={newCreativeTitle}
                  onChange={(e) => setNewCreativeTitle(e.target.value)}
                  placeholder="New creative title"
                />
                <select
                  value={aspect}
                  onChange={(e) => setAspect(e.target.value)}
                  className="h-10 rounded-sm border border-rule bg-paper px-2 text-sm"
                >
                  {["9:16", "1:1", "16:9", "4:5"].map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
                <Button
                  variant="accent"
                  onClick={onCreateCreative}
                  disabled={!newCreativeTitle.trim()}
                >
                  + Creative
                </Button>
              </div>

              {creatives.length === 0 ? (
                <p className="rounded-sm border border-rule bg-paper-2 p-5 text-center text-[13px] text-ink-3">
                  No creatives yet. Create one above, then attach Library
                  assets via the detail page.
                </p>
              ) : (
                <ul className="rounded-sm border border-rule bg-paper-2 divide-y divide-rule">
                  {creatives.map((c) => (
                    <li
                      key={c.id}
                      className="flex items-center justify-between px-4 py-3"
                    >
                      <div className="min-w-0">
                        <div className="text-[13px] font-medium text-ink">{c.title}</div>
                        <div className="text-[11px] text-ink-3">
                          {c.status} · {c.canonical_aspect}
                        </div>
                      </div>
                      <Link
                        href={`/studio/marketing/${c.id}`}
                        className="text-[11px] text-terracotta hover:text-terracotta-2"
                      >
                        Open →
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
