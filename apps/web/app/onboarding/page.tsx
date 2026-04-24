"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import { createBusiness, scrapeBrandFromUrl, upsertBrandLibrary } from "@/lib/api";

type StepKey = "idea" | "analyze" | "swarm" | "plan";
const STEPS: { key: StepKey; label: string }[] = [
  { key: "idea", label: "The idea" },
  { key: "analyze", label: "Atlas analyzes" },
  { key: "swarm", label: "Hire your swarm" },
  { key: "plan", label: "First 30 days" },
];

const STARTER_CHIPS: { label: string; vertical: string; blurb: string }[] = [
  {
    label: "DTC physical",
    vertical: "dtc_physical",
    blurb: "physical-product DTC brand with a Shopify storefront",
  },
  {
    label: "DTC print-on-demand",
    vertical: "dtc_pod",
    blurb: "print-on-demand store using Printful or a comparable supplier",
  },
  {
    label: "SaaS product",
    vertical: "saas",
    blurb: "software product with a landing page and Stripe subscription",
  },
  {
    label: "Local service",
    vertical: "services",
    blurb: "local service business with a simple booking flow",
  },
];

const SPECIALISTS = [
  { name: "Atlas", role: "CEO · Orchestrator", required: true },
  { name: "Creative Director", role: "Brand, copy, visuals", required: true },
  { name: "Product Builder", role: "Storefronts, SKUs, domains", required: true },
  { name: "Ads Operator", role: "Meta, Google, TikTok paid media" },
  { name: "Growth Analyst", role: "Weekly reviews, anomalies" },
  { name: "Social Engagement", role: "Comments, DMs, on-brand replies" },
  { name: "Customer Service", role: "Tickets, refunds, orders" },
  { name: "Finance Ops", role: "Reconciliation, P&L, tax prep" },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<StepKey>("idea");
  const [name, setName] = useState("");
  const [vertical, setVertical] = useState<string>("dtc_physical");
  const [idea, setIdea] = useState(
    "A direct-to-consumer line of minimalist home goods made from natural linen, sold to design-forward renters.",
  );
  const [cap, setCap] = useState(500);
  const [brandUrl, setBrandUrl] = useState("");
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(SPECIALISTS.map((s) => [s.name, true])),
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const activeIndex = STEPS.findIndex((s) => s.key === step);

  async function launch() {
    if (!name.trim()) {
      setStep("idea");
      setErr("Name your venture before launching.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const biz = await createBusiness({
        name: name.trim(),
        vertical,
        weekly_spend_cap_cents: cap * 100,
      });
      // Fire-and-forget: if the user pasted a brand URL, pre-populate
      // the Brand Library in the background. Any failure is silent —
      // they can retry from the Brand Library page.
      const url = brandUrl.trim();
      if (url) {
        void (async () => {
          try {
            const { extracted } = await scrapeBrandFromUrl(biz.id, url);
            await upsertBrandLibrary(biz.id, {
              name: extracted.name || name.trim(),
              tagline: (extracted.tagline as string) ?? null,
              source_url: url,
              palette: extracted.palette ?? {},
              typography: extracted.typography ?? {},
              voice_paragraph: extracted.voice_paragraph ?? null,
            });
          } catch {
            // Silent — user can retry from Brand Library page.
          }
        })();
      }
      router.replace(`/businesses/${biz.id}/launch`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <AppShell breadcrumbs={["Helm", "New venture"]}>
      <div className="px-8 pt-10 pb-20 max-w-3xl mx-auto">
        <div className="mb-8 flex items-center gap-3">
          <div className="h-8 w-8 grid place-items-center rounded-md bg-ink text-paper font-serif text-[20px] leading-none">
            H
          </div>
          <div className="flex-1">
            <div className="text-[13px] font-medium">New venture · onboarding</div>
            <div className="text-[11px] text-ink-3">
              Step {activeIndex + 1} of {STEPS.length} — {STEPS[activeIndex]?.label}
            </div>
          </div>
          <div className="flex gap-1.5">
            {STEPS.map((s, i) => (
              <div
                key={s.key}
                className={cn(
                  "h-1 w-7 rounded-sm",
                  i < activeIndex
                    ? "bg-terracotta"
                    : i === activeIndex
                      ? "bg-ink"
                      : "bg-sand-2",
                )}
              />
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-rule bg-paper p-8 min-h-[440px]">
          {step === "idea" && (
            <StepIdea
              name={name}
              setName={setName}
              idea={idea}
              setIdea={setIdea}
              vertical={vertical}
              setVertical={setVertical}
              cap={cap}
              setCap={setCap}
              brandUrl={brandUrl}
              setBrandUrl={setBrandUrl}
            />
          )}
          {step === "analyze" && (
            <StepAnalyze idea={idea} name={name} vertical={vertical} />
          )}
          {step === "swarm" && (
            <StepSwarm
              enabled={enabled}
              setEnabled={setEnabled}
            />
          )}
          {step === "plan" && <StepPlan name={name} vertical={vertical} cap={cap} />}
        </div>

        {err && (
          <div className="mt-4 rounded-md border border-rose-2/50 bg-rose-soft/50 p-3 text-sm text-rose-2">
            {err}
          </div>
        )}

        <div className="mt-6 flex justify-between">
          <Link
            href="/today"
            className={cn(
              "inline-flex items-center h-11 px-5 rounded-sm border border-rule bg-paper text-sm text-ink hover:bg-sand",
              activeIndex > 0 && "invisible",
            )}
          >
            Cancel
          </Link>
          {activeIndex > 0 && (
            <Button
              variant="outline"
              size="lg"
              onClick={() => setStep(STEPS[activeIndex - 1]!.key)}
            >
              ← Back
            </Button>
          )}
          <Button
            variant="accent"
            size="lg"
            disabled={busy || (step === "idea" && !name.trim())}
            onClick={() => {
              if (step === "plan") void launch();
              else setStep(STEPS[activeIndex + 1]!.key);
            }}
          >
            {step === "plan" ? (
              busy ? (
                "Launching…"
              ) : (
                <>
                  <Icon name="sparkle" size={13} /> Launch venture
                </>
              )
            ) : (
              "Continue →"
            )}
          </Button>
        </div>
      </div>
    </AppShell>
  );
}

function StepIdea({
  name,
  setName,
  idea,
  setIdea,
  vertical,
  setVertical,
  cap,
  setCap,
  brandUrl,
  setBrandUrl,
}: {
  name: string;
  setName: (s: string) => void;
  idea: string;
  setIdea: (s: string) => void;
  vertical: string;
  setVertical: (s: string) => void;
  cap: number;
  setCap: (n: number) => void;
  brandUrl: string;
  setBrandUrl: (s: string) => void;
}) {
  return (
    <div>
      <h2 className="font-serif text-[32px] leading-tight tracking-tightest mb-2">
        What are you bringing to market?
      </h2>
      <p className="text-sm text-ink-3 mb-6">
        Name the venture and describe it in a sentence. Atlas handles the rest.
      </p>

      <div className="space-y-5">
        <div className="space-y-1.5">
          <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
            Venture name
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Olivine Goods"
            maxLength={120}
            required
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
            In a sentence or three
          </label>
          <textarea
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            rows={4}
            className="flex w-full rounded-sm border border-rule bg-paper px-3 py-2 text-[15px] leading-relaxed text-ink focus:outline-none focus:border-ink-2 resize-none"
          />
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium mb-2">
            Starting point
          </div>
          <div className="flex flex-wrap gap-2">
            {STARTER_CHIPS.map((c) => (
              <button
                key={c.vertical}
                type="button"
                onClick={() => setVertical(c.vertical)}
                className={cn(
                  "text-xs px-3 py-1.5 rounded-full border",
                  vertical === c.vertical
                    ? "bg-ink text-paper border-ink"
                    : "bg-paper text-ink-2 border-rule hover:bg-sand",
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
            Existing brand URL <span className="text-ink-3/70 normal-case tracking-normal">(optional)</span>
          </label>
          <Input
            type="url"
            value={brandUrl}
            onChange={(e) => setBrandUrl(e.target.value)}
            placeholder="https://yourbrand.com — we'll auto-fill your Brand Library"
          />
          <p className="text-xs text-ink-3">
            Claude extracts your palette, typography, and voice from the page. Costs about 5¢ in credits.
          </p>
        </div>

        <div>
          <div className="flex items-baseline justify-between mb-2">
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Weekly spend cap
            </label>
            <span className="font-serif text-[22px] tabular">${cap}</span>
          </div>
          <input
            type="range"
            min={50}
            max={5000}
            step={50}
            value={cap}
            onChange={(e) => setCap(Number(e.target.value))}
            className="w-full accent-terracotta"
          />
          <p className="text-xs text-ink-3 mt-1">
            The Stripe-issued card refuses any spend that would push the weekly total past this.
          </p>
        </div>
      </div>
    </div>
  );
}

function StepAnalyze({
  idea,
  name,
  vertical,
}: {
  idea: string;
  name: string;
  vertical: string;
}) {
  const chip = useMemo(
    () => STARTER_CHIPS.find((c) => c.vertical === vertical),
    [vertical],
  );
  return (
    <div>
      <h2 className="font-serif text-[28px] leading-tight tracking-tightest mb-2">
        Atlas is thinking through it.
      </h2>
      <p className="text-sm text-ink-3 mb-6">
        Market, margins, risks, and the simplest shape of the first 90 days for <b>{name || "your venture"}</b>.
      </p>

      <div className="space-y-4">
        <AnalysisItem
          num="01"
          title="Market sizing"
          desc={
            chip
              ? `We'll treat this as ${chip.blurb}. The core play: niche clarity + consistent brand voice beats volume at the scale a single operator runs.`
              : "Positioning this as a focused niche play. Consistency beats breadth at your scale."
          }
        />
        <AnalysisItem
          num="02"
          title="Unit economics (projected)"
          desc={
            vertical === "saas"
              ? "Target LTV:CAC of 3:1+ within 12 months. First 60 days: free-tier + one paid tier, manual onboarding."
              : "Target gross margin 55-65% at launch volumes. Ads pay back within 30 days or Ads Operator kills the campaign."
          }
        />
        <AnalysisItem
          num="03"
          title="Top risks"
          desc={
            vertical === "services"
              ? "Capacity constraints — scale with pricing before hiring. Watch for no-shows (require deposit)."
              : "Supplier concentration, seasonality, ad-account suspension. The swarm flags early and pauses safely."
          }
        />
        <AnalysisItem
          num="04"
          title="How you'll know it's working"
          desc={
            "ROAS > 2.0 sustained for 14 days; repeat-rate > 25% by day 60; NPS > 40 by day 90. Growth Analyst pushes these weekly."
          }
        />
      </div>

      <p className="mt-6 text-xs text-ink-3">
        Pitch: &ldquo;{idea.trim()}&rdquo;
      </p>
    </div>
  );
}

function AnalysisItem({
  num,
  title,
  desc,
}: {
  num: string;
  title: string;
  desc: string;
}) {
  return (
    <div className="flex gap-4 py-3 border-b border-rule last:border-b-0">
      <div className="font-serif text-[20px] text-terracotta w-8 leading-none">{num}</div>
      <div>
        <div className="text-[14px] font-medium mb-1">{title}</div>
        <div className="text-[13px] text-ink-2 leading-relaxed">{desc}</div>
      </div>
    </div>
  );
}

function StepSwarm({
  enabled,
  setEnabled,
}: {
  enabled: Record<string, boolean>;
  setEnabled: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
}) {
  return (
    <div>
      <h2 className="font-serif text-[28px] leading-tight tracking-tightest mb-2">
        Your recommended swarm.
      </h2>
      <p className="text-sm text-ink-3 mb-6">
        Atlas will coordinate. You can adjust any time from Agents.
      </p>

      <div className="grid grid-cols-2 gap-3">
        {SPECIALISTS.map((s) => (
          <div
            key={s.name}
            className={cn(
              "flex items-center gap-3 p-3 rounded-sm border",
              enabled[s.name] ? "border-rule bg-paper-2" : "border-rule bg-paper",
            )}
          >
            <div className="h-8 w-8 grid place-items-center rounded-full bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-sm">
              {s.name[0]}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium">{s.name}</div>
              <div className="text-[11px] text-ink-3">{s.role}</div>
            </div>
            <button
              type="button"
              onClick={() =>
                !s.required &&
                setEnabled((prev) => ({ ...prev, [s.name]: !prev[s.name] }))
              }
              disabled={s.required}
              className={cn(
                "h-4 w-7 rounded-full p-0.5 transition-colors",
                enabled[s.name] ? "bg-ink" : "bg-sand-2",
                s.required ? "opacity-60 cursor-not-allowed" : "",
              )}
              aria-label={`Toggle ${s.name}`}
            >
              <span
                className={cn(
                  "block h-3 w-3 rounded-full bg-paper transition-transform",
                  enabled[s.name] ? "translate-x-3" : "translate-x-0",
                )}
              />
            </button>
          </div>
        ))}
      </div>
      <p className="mt-5 text-xs text-ink-3">
        Atlas and the two build specialists are always on. Others can be toggled later as the
        business needs them.
      </p>
    </div>
  );
}

function StepPlan({
  name,
  vertical,
  cap,
}: {
  name: string;
  vertical: string;
  cap: number;
}) {
  const weeks = useMemo(() => planFor(vertical, cap), [vertical, cap]);
  return (
    <div>
      <h2 className="font-serif text-[28px] leading-tight tracking-tightest mb-2">
        Your first 30 days.
      </h2>
      <p className="text-sm text-ink-3 mb-6">
        A simple plan for <b>{name || "your venture"}</b>. Atlas runs it; you approve the big moments.
      </p>

      <div className="space-y-5">
        {weeks.map((wk) => (
          <div key={wk.label}>
            <div className="text-[11px] uppercase tracking-[0.08em] text-terracotta mb-2 font-medium">
              {wk.label}
            </div>
            <ul className="space-y-1.5">
              {wk.items.map((it) => (
                <li key={it} className="flex items-center gap-2.5 text-[13px]">
                  <div className="h-4 w-4 rounded-sm border border-rule grid place-items-center text-ink-3">
                    <Icon name="check" size={10} />
                  </div>
                  {it}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function planFor(vertical: string, cap: number): { label: string; items: string[] }[] {
  const ad = Math.min(Math.round(cap * 0.6), 300);
  if (vertical === "saas") {
    return [
      {
        label: "Week 1",
        items: [
          "Stripe Billing setup + pricing page (Product Builder)",
          "Landing page v1 with one CTA (Creative Director)",
          "Draft 3 LinkedIn posts + one cold email (Echo)",
        ],
      },
      {
        label: "Week 2",
        items: [
          "Set up analytics events on signup funnel (Pulse)",
          "Onboarding email sequence drafted (Creative Director)",
          "First 10 users reached out to manually (Atlas)",
        ],
      },
      {
        label: "Week 3",
        items: [
          `Begin paid test at $${ad}/week (Ads Operator)`,
          "First customer interview scheduled (Atlas)",
          "Feature-request tracker set up",
        ],
      },
      {
        label: "Week 4",
        items: [
          "Public launch post (ProductHunt, HN) — with your approval",
          "Growth Analyst ships first weekly review",
          "First 20 paid users — celebrate",
        ],
      },
    ];
  }
  if (vertical === "services") {
    return [
      {
        label: "Week 1",
        items: [
          "Booking page + Stripe checkout (Product Builder)",
          "Service descriptions + pricing (Creative Director)",
          "Local-SEO basics (Tide)",
        ],
      },
      {
        label: "Week 2",
        items: [
          "Photo or video for homepage hero (Creative Director)",
          "Intake form that pre-qualifies (Atlas)",
          "First 3 Google reviews from warm contacts",
        ],
      },
      {
        label: "Week 3",
        items: [
          `Geo-targeted Google ads at $${ad}/week (Ads Operator)`,
          "First client delivered — post case study",
          "Set up SMS reminder flow (Sage)",
        ],
      },
      {
        label: "Week 4",
        items: [
          "Public launch on neighborhood channels",
          "Growth Analyst weekly review",
          "Referral program drafted (Echo)",
        ],
      },
    ];
  }
  return [
    {
      label: "Week 1",
      items: [
        "LLC + Stripe Connect (Harbor) — your bank details collected in-flow",
        "Supplier contract locked (Scribe) — for POD we default to Printful",
        "Brand kit v1: name, palette, typography, voice (Creative Director)",
      ],
    },
    {
      label: "Week 2",
      items: [
        "Site v1 on Shopify with 5-10 SKUs (Product Builder)",
        "Draft 3 ad creatives — 15s reel, static hero, carousel (Creative Director)",
        "Set up analytics events (Pulse)",
      ],
    },
    {
      label: "Week 3",
      items: [
        "Soft launch to a small warm list",
        `Begin paid test at $${ad}/week (Ads Operator)`,
        "Customer service templates ready (Sage)",
      ],
    },
    {
      label: "Week 4",
      items: [
        "Public launch across your channels",
        "First wholesale outreach (Echo) if relevant",
        "Weekly review with Atlas",
      ],
    },
  ];
}
