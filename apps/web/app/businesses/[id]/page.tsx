"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ActivityFeed } from "@/components/ActivityFeed";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { type Business, getBusiness, startStripeOnboarding } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

type BusinessDetail = Business & {
  stripe_account_id: string | null;
  brand_kit: Record<string, unknown>;
};

export default function BusinessDetailPage({ params }: PageProps) {
  const { id } = use(params);

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onboarding, setOnboarding] = useState(false);

  useEffect(() => {
    getBusiness(id)
      .then(setBiz)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  async function connectStripe() {
    setOnboarding(true);
    setError(null);
    try {
      const resp = await startStripeOnboarding(id);
      // Pop the onboarding URL in a new tab so the user can return to
      // Helm afterwards. The webhook flips stripe_onboarding_complete.
      window.open(resp.onboarding_url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOnboarding(false);
    }
  }

  if (error && !biz) {
    return (
      <div className="min-h-screen">
        <Nav />
        <main className="max-w-3xl mx-auto px-6 py-8">
          <p className="text-sm text-danger">{error}</p>
          <Link href={{ pathname: "/businesses" }} className="text-sm text-iron mt-4 inline-block">
            ← Back to businesses
          </Link>
        </main>
      </div>
    );
  }

  if (!biz) {
    return (
      <div className="min-h-screen">
        <Nav />
        <main className="max-w-3xl mx-auto px-6 py-8">
          <p className="text-sm text-iron">Loading…</p>
        </main>
      </div>
    );
  }

  const brandName = typeof biz.brand_kit?.name === "string" ? biz.brand_kit.name : null;
  const brandTagline = typeof biz.brand_kit?.tagline === "string" ? biz.brand_kit.tagline : null;

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header className="flex items-baseline justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{biz.name}</h1>
            <p className="text-sm text-iron">
              {biz.vertical} · {biz.status}
            </p>
          </div>
          <Link href={{ pathname: "/chat" }}>
            <Button variant="primary">Open chat</Button>
          </Link>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>Money</CardTitle>
            <CardDescription>
              Stripe Connect + Issuing per business. All spending capped weekly.
            </CardDescription>
          </CardHeader>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-iron">Weekly spend cap</dt>
              <dd className="tabular">${(biz.weekly_spend_cap_cents / 100).toFixed(0)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-iron">Stripe account</dt>
              <dd className="tabular">{biz.stripe_account_id ?? "not connected"}</dd>
            </div>
          </dl>
          <div className="mt-4">
            <Button variant="accent" onClick={connectStripe} disabled={onboarding}>
              {onboarding
                ? "Opening Stripe…"
                : biz.stripe_account_id
                  ? "Resume Stripe onboarding"
                  : "Connect Stripe"}
            </Button>
            {error && <p className="text-sm text-danger mt-3">{error}</p>}
          </div>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Brand</CardTitle>
            <CardDescription>
              What Creative Director set up. Ask the CEO to refine it from the chat.
            </CardDescription>
          </CardHeader>
          {brandName ? (
            <div className="text-sm space-y-1">
              <div className="font-medium">{brandName}</div>
              {brandTagline && <div className="text-iron">{brandTagline}</div>}
            </div>
          ) : (
            <p className="text-sm text-iron">
              No brand kit yet. Go to chat and ask Creative Director to draft one.
            </p>
          )}
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
            <CardDescription>
              Every tool call, approval, and spend. Event-sourced — this is the record.
            </CardDescription>
          </CardHeader>
          <ActivityFeed businessId={id} />
        </Card>

        <Link
          href={{ pathname: "/businesses" }}
          className="text-sm text-iron hover:text-ink dark:hover:text-paper inline-block"
        >
          ← All businesses
        </Link>
      </main>
    </div>
  );
}
