import Link from "next/link";
import { Button } from "@/components/ui/Button";

export const metadata = {
  title: "Pricing — Helm",
  description: "Three tiers. Founder, Operator, Portfolio. Hard caps, no surprise overage.",
};

const TIERS = [
  {
    name: "Founder",
    price: "$199",
    cadence: "/month",
    summary: "Run your first three businesses end-to-end.",
    includes: [
      "3 businesses",
      "2M agent tokens / month",
      "Per-business Stripe Issuing card",
      "Every approval surface",
      "Push notifications + voice input",
      "All 8 specialists, all 3 surfaces",
    ],
  },
  {
    name: "Operator",
    price: "$499",
    cadence: "/month",
    summary: "For operators running a portfolio.",
    includes: [
      "10 businesses",
      "10M agent tokens / month",
      "Priority specialist queue",
      "Weekly Growth Analyst brief",
      "Everything in Founder",
    ],
    highlighted: true,
  },
  {
    name: "Portfolio",
    price: "Custom",
    cadence: "",
    summary: "When the portfolio outgrows even Operator.",
    includes: [
      "Unlimited businesses",
      "Unlimited token budget",
      "Dedicated onboarding",
      "SLA + named support",
      "Computer-use compute on us",
    ],
  },
];

const FAQ = [
  {
    q: "What happens if I hit my token limit?",
    a: "Helm tells you. We don't surprise-charge — agents pause at the cap and we surface a single 'extend or wait' approval. Overage is opt-in.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes. Stripe Customer Portal handles cancel + plan changes. We close the businesses gracefully and you keep export access for 30 days.",
  },
  {
    q: "What about the Stripe-issued card?",
    a: "One virtual card per business, weekly + per-authorization caps you control. We program the card itself with the limits — it's not just our software gate.",
  },
  {
    q: "Is the agent really autonomous?",
    a: "Within the rails you set. Spend > $100 needs your approval. Publishing under your name needs your approval. The kill switch halts every agent across every business in under one second.",
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-paper text-ink paper-grain">
      <header className="flex items-center justify-between px-8 py-5 max-w-6xl mx-auto">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="h-8 w-8 grid place-items-center rounded-md bg-ink text-paper font-serif text-[22px] leading-none">
            H
          </div>
          <span className="text-[18px] font-semibold tracking-tight">Helm</span>
        </Link>
        <Link href="/sign-in">
          <Button variant="accent">Get started</Button>
        </Link>
      </header>

      <section className="max-w-3xl mx-auto px-8 py-20 text-center">
        <div className="text-[11px] font-medium tracking-[0.12em] text-terracotta uppercase mb-6">
          Pricing
        </div>
        <h1 className="font-serif text-5xl md:text-[64px] leading-[1.05] tracking-tightest mb-6">
          Three tiers. Hard caps.
          <br />
          <em className="not-italic text-terracotta">No surprises.</em>
        </h1>
        <p className="text-ink-2 text-[17px] leading-relaxed max-w-2xl mx-auto">
          Every plan includes the full agent swarm, every specialist, every surface. Tiers gate how
          many businesses you run and how much agent compute is included.
        </p>
      </section>

      <section className="max-w-5xl mx-auto px-8 pb-20 grid md:grid-cols-3 gap-5">
        {TIERS.map((t) => (
          <div
            key={t.name}
            className={
              t.highlighted
                ? "rounded-md p-7 flex flex-col bg-ink text-paper border-2 border-terracotta"
                : "rounded-md p-7 flex flex-col bg-paper border border-rule"
            }
          >
            <div
              className={`text-[11px] font-medium tracking-[0.08em] uppercase mb-3 ${t.highlighted ? "text-terracotta-soft" : "text-ink-3"}`}
            >
              {t.name}
            </div>
            <div className="mb-3">
              <span className="font-serif text-[40px] tabular leading-none">{t.price}</span>
              <span className={`text-sm ${t.highlighted ? "opacity-60" : "text-ink-3"} ml-1`}>
                {t.cadence}
              </span>
            </div>
            <p className={`text-sm mb-5 ${t.highlighted ? "opacity-80" : "text-ink-2"}`}>
              {t.summary}
            </p>
            <ul className="text-sm space-y-2 mb-7 flex-1">
              {t.includes.map((line) => (
                <li key={line} className="flex gap-2.5">
                  <span className="text-terracotta">✓</span>
                  <span>{line}</span>
                </li>
              ))}
            </ul>
            {t.name === "Portfolio" ? (
              <a
                href="mailto:hello@helm.app?subject=Portfolio%20tier%20inquiry"
                className="inline-flex items-center justify-center h-11 px-5 rounded-sm bg-terracotta text-paper text-sm font-medium border border-terracotta hover:bg-terracotta-2"
              >
                Talk to us
              </a>
            ) : (
              <Link
                href={{
                  pathname: "/sign-in",
                  query: { upgrade: t.name.toLowerCase() },
                }}
                className={
                  t.highlighted
                    ? "inline-flex items-center justify-center h-11 px-5 rounded-sm bg-terracotta text-paper border border-terracotta hover:bg-terracotta-2 text-sm font-medium"
                    : "inline-flex items-center justify-center h-11 px-5 rounded-sm bg-ink text-paper border border-ink hover:bg-terracotta hover:border-terracotta text-sm font-medium"
                }
              >
                Get {t.name}
              </Link>
            )}
          </div>
        ))}
      </section>

      <section className="max-w-3xl mx-auto px-8 pb-24">
        <h2 className="text-[11px] font-medium tracking-[0.08em] text-ink-3 uppercase mb-7">
          Common questions
        </h2>
        <dl className="space-y-6">
          {FAQ.map((item) => (
            <div key={item.q} className="border-b border-rule pb-6">
              <dt className="text-base font-medium mb-2">{item.q}</dt>
              <dd className="text-sm text-ink-2 leading-relaxed">{item.a}</dd>
            </div>
          ))}
        </dl>
      </section>

      <footer className="max-w-6xl mx-auto px-8 py-10 text-xs text-ink-3 flex items-center justify-between border-t border-rule">
        <Link href="/" className="hover:text-ink">
          ← Back to Helm
        </Link>
        <a href="mailto:hello@helm.app" className="hover:text-ink">
          hello@helm.app
        </a>
      </footer>
    </div>
  );
}
