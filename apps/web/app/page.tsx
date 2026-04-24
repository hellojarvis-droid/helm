import Link from "next/link";
import { redirect } from "next/navigation";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { supabaseServer } from "@/lib/supabase/server";

export default async function Home() {
  const supabase = await supabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) redirect("/today");

  return (
    <div className="min-h-screen bg-paper text-ink paper-grain">
      <Header />
      <Hero />
      <Surfaces />
      <HowItWorks />
      <Pricing />
      <SafetyRails />
      <Footer />
    </div>
  );
}

function Header() {
  return (
    <header className="flex items-center justify-between px-8 py-5 max-w-6xl mx-auto">
      <div className="flex items-center gap-2.5">
        <div className="h-8 w-8 grid place-items-center rounded-md bg-ink text-paper font-serif text-[22px] leading-none">
          H
        </div>
        <span className="text-[18px] font-semibold tracking-tight">Helm</span>
      </div>
      <div className="flex items-center gap-6">
        <Link href="/pricing" className="text-sm text-ink-2 hover:text-ink">
          Pricing
        </Link>
        <Link href="/sign-in" className="text-sm text-ink-2 hover:text-ink">
          Sign in
        </Link>
        <Link href="/sign-in">
          <Button variant="accent">Get started</Button>
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="max-w-4xl mx-auto px-8 pt-20 pb-28 text-center">
      <div className="text-[11px] font-medium tracking-[0.12em] text-terracotta uppercase mb-6">
        The operating system for one-person holding companies
      </div>
      <h1 className="font-serif text-5xl md:text-[76px] leading-[1.02] tracking-tightest mb-8">
        One CEO Agent.
        <br />
        Eight specialists.
        <br />
        <em className="text-terracotta not-italic">Every business, autonomous.</em>
      </h1>
      <p className="text-[17px] text-ink-2 max-w-2xl mx-auto leading-relaxed">
        Tell your CEO Agent what to build. It delegates to Idea Scout, Product Builder, Creative
        Director, Ads Operator, Growth Analyst, Social, Customer Service, and Finance. Every
        business runs on a real Stripe-issued virtual card with hard weekly caps, per-authorization
        caps, and an MCC allowlist.
      </p>
      <div className="flex items-center justify-center gap-3 mt-10">
        <Link href="/sign-in">
          <Button variant="accent" size="lg">
            <Icon name="sparkle" size={14} /> Start a business
          </Button>
        </Link>
        <a
          href="#how"
          className="inline-flex items-center h-11 px-5 text-sm rounded-sm border border-rule bg-paper hover:bg-sand"
        >
          How it works
        </a>
      </div>
    </section>
  );
}

function Surfaces() {
  const items = [
    {
      title: "Mobile",
      body: "Command surface in your pocket. Approval pushes buzz the phone. One-tap approve, deny, or raise the weekly cap.",
    },
    {
      title: "Web",
      body: "Deep-dive dashboard. Today, Activity, Spend, Approvals, Safety, Billing — the same data the CEO Agent reads.",
    },
    {
      title: "Desktop",
      body: "For tasks no API covers. Computer-use sessions run sandboxed; you watch what the agent does on your screen.",
    },
  ];
  return (
    <section className="max-w-5xl mx-auto px-8 py-16 grid md:grid-cols-3 gap-5">
      {items.map((it) => (
        <div key={it.title} className="rounded-md border border-rule bg-paper p-6">
          <div className="text-[11px] font-medium tracking-[0.08em] text-ink-3 uppercase mb-3">
            {it.title}
          </div>
          <p className="text-sm leading-relaxed text-ink-2">{it.body}</p>
        </div>
      ))}
    </section>
  );
}

function HowItWorks() {
  const steps = [
    {
      n: "01",
      title: "Describe the business",
      body: "Tell the CEO Agent what kind of business you want to run. It delegates Idea Scout to find a proven concept and Creative Director to produce a brand kit.",
    },
    {
      n: "02",
      title: "Watch the launch",
      body: "Product Builder stands up the Shopify store, loads SKUs, writes policies. Ads Operator queues the first paid test. You approve the spend — one tap.",
    },
    {
      n: "03",
      title: "Stay in the loop",
      body: "Every spend goes through approval rules coded into Helm. Every action is event-sourced; the Activity log is the record. Kill switch halts everything in under a second.",
    },
  ];
  return (
    <section id="how" className="max-w-4xl mx-auto px-8 py-20">
      <div className="text-[11px] font-medium tracking-[0.08em] text-ink-3 uppercase mb-8">
        How it works
      </div>
      <div className="space-y-12">
        {steps.map((s) => (
          <div key={s.n} className="flex gap-6">
            <div className="font-serif text-[44px] text-terracotta leading-none tabular">
              {s.n}
            </div>
            <div className="flex-1 pt-1">
              <h3 className="text-[20px] font-semibold tracking-tight mb-2">{s.title}</h3>
              <p className="text-ink-2 leading-relaxed">{s.body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Pricing() {
  const tiers = [
    {
      name: "Founder",
      price: "$199",
      cadence: "/month",
      includes: [
        "3 businesses",
        "2M agent tokens / month",
        "Per-business Stripe Issuing card",
        "Every approval surface",
      ],
    },
    {
      name: "Operator",
      price: "$499",
      cadence: "/month",
      includes: [
        "10 businesses",
        "10M agent tokens / month",
        "Priority specialist queue",
        "Weekly Growth Analyst brief",
      ],
      highlighted: true,
    },
    {
      name: "Portfolio",
      price: "Custom",
      cadence: "",
      includes: [
        "Unlimited businesses",
        "Unlimited token budget",
        "Dedicated onboarding",
        "SLA + named support",
      ],
    },
  ];
  return (
    <section className="max-w-5xl mx-auto px-8 py-20">
      <div className="text-[11px] font-medium tracking-[0.08em] text-ink-3 uppercase mb-8 text-center">
        Pricing
      </div>
      <div className="grid md:grid-cols-3 gap-5">
        {tiers.map((t) => (
          <div
            key={t.name}
            className={
              t.highlighted
                ? "rounded-md p-6 bg-ink text-paper border-2 border-terracotta"
                : "rounded-md p-6 bg-paper border border-rule"
            }
          >
            <div
              className={`text-[11px] font-medium tracking-[0.08em] uppercase mb-3 ${t.highlighted ? "text-terracotta-soft" : "text-ink-3"}`}
            >
              {t.name}
            </div>
            <div className="mb-5">
              <span className="font-serif text-[36px] tabular leading-none">{t.price}</span>
              <span
                className={`text-sm ${t.highlighted ? "opacity-60" : "text-ink-3"} ml-1`}
              >
                {t.cadence}
              </span>
            </div>
            <ul className="text-sm space-y-2">
              {t.includes.map((line) => (
                <li key={line} className="flex gap-2.5">
                  <span className={t.highlighted ? "text-terracotta" : "text-terracotta"}>
                    ✓
                  </span>
                  {line}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function SafetyRails() {
  return (
    <section className="max-w-4xl mx-auto px-8 py-20 text-center">
      <div className="text-[11px] font-medium tracking-[0.12em] text-terracotta uppercase mb-4">
        Safety rails, not seatbelts
      </div>
      <h2 className="font-serif text-[44px] leading-tight tracking-tightest mb-5">
        Agent autonomy, with your money fully in scope.
      </h2>
      <p className="text-ink-2 max-w-2xl mx-auto leading-relaxed">
        Every spend goes through a programmatic allowlist (Stripe MCC categories), per-authorization
        caps, and a weekly cap pushed to the Stripe card itself. A single tap halts every running
        agent across every business within one second. Every decision is event-sourced and
        replayable — there&apos;s no black box.
      </p>
    </section>
  );
}

function Footer() {
  return (
    <footer className="max-w-6xl mx-auto px-8 py-10 text-xs text-ink-3 flex items-center justify-between border-t border-rule">
      <div>Helm · 2026</div>
      <div className="flex gap-4">
        <Link href="/pricing" className="hover:text-ink">
          Pricing
        </Link>
        <Link href="/terms" className="hover:text-ink">
          Terms
        </Link>
        <Link href="/privacy" className="hover:text-ink">
          Privacy
        </Link>
        <a href="mailto:hello@helm.app" className="hover:text-ink">
          Contact
        </a>
        <Link href="/sign-in" className="hover:text-ink">
          Sign in
        </Link>
      </div>
    </footer>
  );
}
