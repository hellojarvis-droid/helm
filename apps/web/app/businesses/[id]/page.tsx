"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { EditCapsModal } from "@/components/EditCapsModal";
import { SpendCard } from "@/components/SpendCard";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import {
  type BusinessDetail,
  type SyncStatus,
  getBusiness,
  getBusinessSyncStatus,
  startStripeOnboarding,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function BusinessDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  // `?stripe=return` — Stripe sent the user back after the onboarding session.
  // `?stripe=refresh` — the signed link expired; they need a new one.
  const stripeReturn = searchParams.get("stripe");

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onboarding, setOnboarding] = useState(false);
  const [editCapsOpen, setEditCapsOpen] = useState(false);
  const [syncStatuses, setSyncStatuses] = useState<SyncStatus[]>([]);

  useEffect(() => {
    getBusiness(id)
      .then(setBiz)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getBusinessSyncStatus(id)
      .then(setSyncStatuses)
      .catch(() => {
        // Non-fatal: no sync records is normal for a fresh business.
      });
  }, [id]);

  // After Stripe redirects back with ?stripe=return, poll briefly so the
  // webhook's flip of `stripe_onboarding_complete` is visible without a
  // manual refresh. We don't hammer — four probes over ~8 seconds, then stop.
  useEffect(() => {
    if (stripeReturn !== "return") return;
    let cancelled = false;
    let attempts = 0;
    const iv = setInterval(async () => {
      attempts += 1;
      try {
        const fresh = await getBusiness(id);
        if (!cancelled) setBiz(fresh);
        if (fresh.stripe_onboarding_complete || attempts >= 4) clearInterval(iv);
      } catch {
        if (attempts >= 4) clearInterval(iv);
      }
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [id, stripeReturn]);

  async function connectStripe() {
    setOnboarding(true);
    setError(null);
    try {
      const resp = await startStripeOnboarding(id);
      // Full-page redirect — window.open() after an await is blocked by every
      // modern browser's popup heuristic because the async gap breaks the
      // user-gesture chain. Stripe's hosted onboarding is meant to own the
      // top-level document anyway; our return_url brings the user back here.
      window.location.href = resp.onboarding_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setOnboarding(false);
    }
  }

  if (error && !biz) {
    return (
      <AppShell breadcrumbs={["Helm", "Businesses", "Detail"]}>
        <div className="px-10 py-10 max-w-3xl">
          <p className="text-sm text-rose-2">{error}</p>
          <Link href="/businesses" className="text-sm text-ink-3 mt-4 inline-block hover:text-ink">
            ← Back to businesses
          </Link>
        </div>
      </AppShell>
    );
  }

  if (!biz) {
    return (
      <AppShell breadcrumbs={["Helm", "Businesses", "Detail"]}>
        <div className="px-10 py-10">
          <p className="text-sm text-ink-3">Loading…</p>
        </div>
      </AppShell>
    );
  }

  const brandName = typeof biz.brand_kit?.name === "string" ? biz.brand_kit.name : null;
  const brandTagline = typeof biz.brand_kit?.tagline === "string" ? biz.brand_kit.tagline : null;

  return (
    <AppShell breadcrumbs={["Helm", "Businesses", biz.name]}>
      <div className="px-10 pt-8 pb-20 max-w-4xl">
        {syncStatuses.some((s) => s.last_status === "conflict") && (
          <SyncConflictBanner
            conflicts={syncStatuses.filter((s) => s.last_status === "conflict")}
          />
        )}
        {stripeReturn === "return" && (
          <div
            className={`mb-5 rounded-md border p-4 text-sm ${
              biz.stripe_onboarding_complete
                ? "border-sage/50 bg-sage-soft/50 text-sage-2"
                : "border-amber-2/40 bg-amber-soft/50 text-amber-2"
            }`}
          >
            {biz.stripe_onboarding_complete ? (
              <>
                <strong className="font-semibold">Stripe connected.</strong> Onboarding is
                complete — this business can accept payments and Harbor can request an issuing
                card.
              </>
            ) : (
              <>
                <strong className="font-semibold">Back from Stripe.</strong> Your submission is
                being reviewed; we&apos;ll flip this to &ldquo;connected&rdquo; as soon as
                Stripe&apos;s webhook lands. Usually a few seconds.
              </>
            )}
          </div>
        )}
        {stripeReturn === "refresh" && (
          <div className="mb-5 rounded-md border border-rule bg-paper-2 p-4 text-sm text-ink-2">
            Your Stripe onboarding link expired — click <strong>Resume Stripe onboarding</strong>{" "}
            below to mint a fresh one.
          </div>
        )}
        <header className="flex items-end justify-between mb-7">
          <div>
            <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">
              {biz.status} · {prettyVertical(biz.vertical)}
            </div>
            <h1 className="font-serif text-[44px] leading-none tracking-tightest">{biz.name}</h1>
          </div>
          <Link
            href="/chat"
            className="inline-flex items-center gap-1.5 px-3.5 h-9 text-[13px] rounded-sm bg-ink border border-ink text-paper hover:bg-terracotta hover:border-terracotta"
          >
            <Icon name="sparkle" size={13} /> Open chat
          </Link>
        </header>

        <div className="grid grid-cols-12 gap-5">
          <Card className="col-span-7">
            <CardHeader>
              <CardTitle>Money</CardTitle>
              <CardDescription>
                Stripe Connect + Issuing per business. All spend capped weekly.
              </CardDescription>
            </CardHeader>
            <dl className="space-y-2 text-sm">
              <Row
                label="Weekly spend cap"
                value={`$${(biz.weekly_spend_cap_cents / 100).toFixed(0)}`}
              />
              <Row
                label="Per-authorization cap"
                value={`$${(biz.per_auth_cap_cents / 100).toFixed(0)}`}
              />
              <Row
                label="MCC allowlist"
                value={
                  biz.allowed_mcc_codes === null
                    ? "default"
                    : biz.allowed_mcc_codes.length === 0
                      ? "none (locked)"
                      : `custom (${biz.allowed_mcc_codes.length})`
                }
              />
              <Row label="Stripe account" value={biz.stripe_account_id ?? "not connected"} />
            </dl>
            <SyncChips syncStatuses={syncStatuses} />
            {biz.stripe_sync?.attempted && biz.stripe_sync.synced === false ? (
              <p className="text-sm text-rose-2 mt-3">
                Stripe sync failed: {biz.stripe_sync.error ?? "unknown error"}. Caps updated in our
                DB but Stripe&apos;s card-level limit may still decline real transactions. Try
                saving again.
              </p>
            ) : null}
            <div className="mt-5 flex gap-2">
              <Button variant="accent" onClick={connectStripe} disabled={onboarding}>
                {onboarding
                  ? "Opening Stripe…"
                  : biz.stripe_account_id
                    ? "Resume Stripe onboarding"
                    : "Connect Stripe"}
              </Button>
              <Button variant="outline" onClick={() => setEditCapsOpen(true)}>
                Edit caps
              </Button>
            </div>
            {error && <p className="text-sm text-rose-2 mt-3">{error}</p>}
          </Card>

          <div className="col-span-5">
            <SpendCard businessId={id} />
          </div>

          <Card className="col-span-6">
            <CardHeader>
              <CardTitle>Brand</CardTitle>
              <CardDescription>
                Every specialist pulls palette, voice, and moodboard from here.
              </CardDescription>
            </CardHeader>
            {brandName ? (
              <div className="text-sm space-y-1">
                <div className="font-serif text-[22px] leading-tight text-ink">{brandName}</div>
                {brandTagline && <div className="text-ink-3">{brandTagline}</div>}
              </div>
            ) : (
              <p className="text-sm text-ink-3">
                No brand kit yet. Paste a URL in the Brand Library to auto-fill.
              </p>
            )}
            <Link
              href={`/businesses/${id}/brand-library`}
              className="mt-3 inline-flex items-center gap-1 text-[12px] text-terracotta hover:text-terracotta-2"
            >
              Open Brand Library →
            </Link>
          </Card>

          <Card className="col-span-6">
            <CardHeader>
              <CardTitle>Quick actions</CardTitle>
              <CardDescription>Common moves for this business.</CardDescription>
            </CardHeader>
            <div className="flex flex-col gap-2">
              <Link
                href={`/businesses/${id}/integrations`}
                className="flex items-center justify-between p-3 rounded-sm border border-rule bg-paper-2 hover:bg-sand text-sm"
              >
                <span>Integrations (Shopify, Meta Ads, …)</span>
                <Icon name="tweaks" size={14} />
              </Link>
              <Link
                href={`/businesses/${id}/storefront`}
                className="flex items-center justify-between p-3 rounded-sm border border-rule bg-paper-2 hover:bg-sand text-sm"
              >
                <span>Helm Storefront</span>
                <Icon name="card" size={14} />
              </Link>
              <Link
                href={`/businesses/${id}/library`}
                className="flex items-center justify-between p-3 rounded-sm border border-rule bg-paper-2 hover:bg-sand text-sm"
              >
                <span>Creative Library</span>
                <Icon name="folder" size={14} />
              </Link>
              <Link
                href={`/businesses/${id}/expenses`}
                className="flex items-center justify-between p-3 rounded-sm border border-rule bg-paper-2 hover:bg-sand text-sm"
              >
                <span>Expenses &amp; tax export</span>
                <Icon name="receipt" size={14} />
              </Link>
              <Link
                href="/chat"
                className="flex items-center justify-between p-3 rounded-sm border border-rule bg-paper-2 hover:bg-sand text-sm"
              >
                <span>Ask Atlas about this business</span>
                <Icon name="sparkle" size={14} />
              </Link>
              <Link
                href="/approvals"
                className="flex items-center justify-between p-3 rounded-sm border border-rule bg-paper-2 hover:bg-sand text-sm"
              >
                <span>Review approvals</span>
                <Icon name="check" size={14} />
              </Link>
              <Link
                href="/safety"
                className="flex items-center justify-between p-3 rounded-sm border border-rule bg-paper-2 hover:bg-sand text-sm"
              >
                <span>Kill switch</span>
                <Icon name="shield" size={14} />
              </Link>
            </div>
          </Card>

        </div>

        <div className="mt-8 flex items-center gap-5">
          <Link
            href="/businesses"
            className="text-sm text-ink-3 hover:text-ink"
          >
            ← All businesses
          </Link>
          <Link
            href={`/events?business_id=${id}`}
            className="text-sm text-ink-3 hover:text-ink inline-flex items-center gap-1.5"
          >
            <Icon name="book" size={13} /> View activity log
          </Link>
        </div>
      </div>

      {editCapsOpen && biz ? (
        <EditCapsModal
          business={biz}
          onClose={() => setEditCapsOpen(false)}
          onSaved={(updated) => {
            setBiz(updated);
            if (!updated.stripe_sync?.attempted || updated.stripe_sync?.synced) {
              setEditCapsOpen(false);
            }
          }}
        />
      ) : null}
    </AppShell>
  );
}

function SyncConflictBanner({ conflicts }: { conflicts: SyncStatus[] }) {
  // "Helm wins" means the external system's change landed AFTER ours but
  // the external event carried an older timestamp. We ignored it so the
  // user's intent stays. Surfacing it gives the user a clear mental model
  // (not a silent merge) and a deliberate next step.
  return (
    <div className="mb-5 rounded-md border border-amber-2/50 bg-amber-soft/50 p-4 text-sm text-amber-2">
      <div className="flex items-start gap-3">
        <Icon name="sparkle" size={16} className="mt-0.5 shrink-0" />
        <div className="flex-1">
          <div className="font-semibold mb-1">
            External change ignored — your edit stands.
          </div>
          {conflicts.map((c) => (
            <div key={`${c.entity_type}:${c.external_id}`} className="text-[13px] mb-1">
              <span className="font-mono">{prettyEntity(c.entity_type)}</span>: a change arrived
              from the provider with an earlier timestamp than your last edit (
              {timeAgo(new Date(c.local_updated_at))}
              {c.external_updated_at &&
                ` · external event from ${timeAgo(new Date(c.external_updated_at))}`}
              ). Helm keeps your value; save again to re-confirm and clear this flag.
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SyncChips({ syncStatuses }: { syncStatuses: SyncStatus[] }) {
  if (syncStatuses.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 mt-4 mb-1">
      {syncStatuses.map((s) => (
        <SyncChip key={`${s.entity_type}:${s.external_id}`} status={s} />
      ))}
    </div>
  );
}

function SyncChip({ status }: { status: SyncStatus }) {
  const label = prettyEntity(status.entity_type);
  const when = timeAgo(new Date(status.local_updated_at));
  const via = status.last_direction === "push" ? "pushed" : "pulled via webhook";
  const tone =
    status.last_status === "ok"
      ? "chip-sage"
      : status.last_status === "conflict"
        ? "chip-amber"
        : "chip-rose";
  return (
    <span
      className={cn("chip", tone)}
      title={status.last_error ?? `${label} · ${via} ${when}`}
    >
      {label} · {status.last_status === "conflict" ? "conflict" : `${via} ${when}`}
    </span>
  );
}

function prettyEntity(t: string): string {
  const MAP: Record<string, string> = {
    stripe_card_caps: "Stripe caps",
    shopify_product: "Shopify product",
    connection_status: "Connection",
  };
  return MAP[t] ?? t;
}

function timeAgo(when: Date): string {
  const s = Math.round((Date.now() - when.getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1 border-b border-rule last:border-b-0">
      <dt className="text-ink-3">{label}</dt>
      <dd className="font-mono text-xs text-ink">{value}</dd>
    </div>
  );
}

function prettyVertical(v: string) {
  const MAP: Record<string, string> = {
    dtc_physical: "DTC physical",
    dtc_pod: "DTC print-on-demand",
    saas: "SaaS",
    services: "Services",
  };
  return MAP[v] ?? v;
}
