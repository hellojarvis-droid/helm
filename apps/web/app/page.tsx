import Link from "next/link";
import { redirect } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { supabaseServer } from "@/lib/supabase/server";

export default async function Home() {
  const supabase = await supabaseServer();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) redirect("/today");

  return (
    <div className="min-h-screen bg-paper text-ink">
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
    <header className="flex items-center justify-between px-6 py-4 max-w-6xl mx-auto">
      <div className="text-lg font-semibold tracking-tight">Helm</div>
      <div className="flex items-center gap-4">
        <Link href={{ pathname: "/sign-in" }} className="text-sm text-iron hover:text-ink">
          Sign in
        </Link>
        <Link href={{ pathname: "/sign-in" }}>
          <Button variant="accent">Get started</Button>
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="max-w-4xl mx-auto px-6 py-24 text-center">
      <div className="text-xs font-semibold tracking-widest text-accent uppercase mb-4">
        The OS for one-person holding companies
      </div>
      <h1 className="text-5xl md:text-6xl font-semibold tracking-tight leading-tight mb-6">
        One CEO Agent.
        <br />
        Eight specialists.
        <br />
        Every business, autonomous.
      </h1>
      <p className="text-lg text-iron max-w-2xl mx-auto leading-relaxed">
        Tell your CEO Agent what to build. It delegates to Idea Scout, Product Builder, Creative
        Director, Ads Operator, Growth Analyst, Social, Customer Service, and Finance. Every
        business runs on a real Stripe-issued virtual card with hard weekly caps, per-authorization
        caps, and an MCC allowlist.
      </p>
      <div className="flex items-center justify-center gap-3 mt-10">
        <Link href={{ pathname: "/sign-in" }}>
          <Button variant="accent" size="lg">
            Start a business →
          </Button>
        </Link>
        <a
          href="#how"
          className="inline-flex items-center h-12 px-6 text-base rounded-md border border-iron/30 hover:bg-haze"
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
    <section className="max-w-5xl mx-auto px-6 py-20 grid md:grid-cols-3 gap-6">
      {items.map((it) => (
        <div
          key={it.title}
          className="rounded-xl border border-iron/20 bg-haze/30 dark:bg-ink/20 p-6"
        >
          <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-2">
            {it.title}
          </div>
          <p className="text-sm leading-relaxed">{it.body}</p>
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
    <section id="how" className="max-w-4xl mx-auto px-6 py-20">
      <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-8">
        How it works
      </div>
      <div className="space-y-10">
        {steps.map((s) => (
          <div key={s.n} className="flex gap-6">
            <div className="text-4xl font-semibold tabular text-accent">{s.n}</div>
            <div>
              <h3 className="text-xl font-semibold mb-2">{s.title}</h3>
              <p className="text-iron leading-relaxed">{s.body}</p>
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
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-8 text-center">
        Pricing
      </div>
      <div className="grid md:grid-cols-3 gap-6">
        {tiers.map((t) => (
          <div
            key={t.name}
            className={`rounded-xl p-6 ${
              t.highlighted
                ? "bg-ink text-paper border-2 border-accent"
                : "bg-haze/40 dark:bg-ink/20 border border-iron/20"
            }`}
          >
            <div className="text-xs font-semibold tracking-widest uppercase mb-2 opacity-80">
              {t.name}
            </div>
            <div className="mb-4">
              <span className="text-3xl font-semibold tabular">{t.price}</span>
              <span className="text-sm opacity-60">{t.cadence}</span>
            </div>
            <ul className="text-sm space-y-2">
              {t.includes.map((line) => (
                <li key={line} className="flex gap-2">
                  <span className="text-accent">✓</span>
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
    <section className="max-w-4xl mx-auto px-6 py-20 text-center">
      <div className="text-xs font-semibold tracking-widest text-accent uppercase mb-4">
        Safety rails, not seatbelts
      </div>
      <h2 className="text-3xl font-semibold tracking-tight mb-4">
        Agent autonomy, with your money fully in scope.
      </h2>
      <p className="text-iron max-w-2xl mx-auto leading-relaxed">
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
    <footer className="max-w-6xl mx-auto px-6 py-10 text-xs text-iron flex items-center justify-between border-t border-iron/10">
      <div>Helm · 2026</div>
      <div className="flex gap-4">
        <a href="mailto:hello@helm.app" className="hover:text-ink">
          Contact
        </a>
        <Link href={{ pathname: "/sign-in" }} className="hover:text-ink">
          Sign in
        </Link>
      </div>
    </footer>
  );
}
