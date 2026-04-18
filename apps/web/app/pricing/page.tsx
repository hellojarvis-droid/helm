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
    <div className="min-h-screen bg-paper text-ink">
      <header className="flex items-center justify-between px-6 py-4 max-w-6xl mx-auto">
        <Link href={{ pathname: "/" }} className="text-lg font-semibold tracking-tight">
          Helm
        </Link>
        <Link href={{ pathname: "/sign-in" }}>
          <Button variant="accent">Get started</Button>
        </Link>
      </header>

      <section className="max-w-3xl mx-auto px-6 py-16 text-center">
        <div className="text-xs font-semibold tracking-widest text-accent uppercase mb-3">
          Pricing
        </div>
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight mb-4">
          Three tiers. Hard caps. No surprises.
        </h1>
        <p className="text-iron text-lg leading-relaxed max-w-2xl mx-auto">
          Every plan includes the full agent swarm, every specialist, every surface. Tiers gate how
          many businesses you run and how much agent compute is included.
        </p>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-20 grid md:grid-cols-3 gap-6">
        {TIERS.map((t) => (
          <div
            key={t.name}
            className={`rounded-xl p-6 flex flex-col ${
              t.highlighted
                ? "bg-ink text-paper border-2 border-accent"
                : "bg-haze/40 dark:bg-ink/20 border border-iron/20"
            }`}
          >
            <div className="text-xs font-semibold tracking-widest uppercase mb-2 opacity-80">
              {t.name}
            </div>
            <div className="mb-2">
              <span className="text-3xl font-semibold tabular">{t.price}</span>
              <span className="text-sm opacity-60">{t.cadence}</span>
            </div>
            <p className="text-sm opacity-80 mb-4">{t.summary}</p>
            <ul className="text-sm space-y-2 mb-6 flex-1">
              {t.includes.map((line) => (
                <li key={line} className="flex gap-2">
                  <span className="text-accent">✓</span>
                  <span>{line}</span>
                </li>
              ))}
            </ul>
            {t.name === "Portfolio" ? (
              <a
                href="mailto:hello@helm.app?subject=Portfolio%20tier%20inquiry"
                className="inline-flex items-center justify-center h-11 px-5 rounded-md bg-accent text-paper text-sm font-medium hover:bg-accent/90"
              >
                Talk to us
              </a>
            ) : (
              <Link
                href={{
                  pathname: "/sign-in",
                  query: { upgrade: t.name.toLowerCase() },
                }}
                className={`inline-flex items-center justify-center h-11 px-5 rounded-md text-sm font-medium ${
                  t.highlighted
                    ? "bg-accent text-paper hover:bg-accent/90"
                    : "bg-ink text-paper hover:bg-ink/90 dark:bg-paper dark:text-ink dark:hover:bg-paper/90"
                }`}
              >
                Get {t.name}
              </Link>
            )}
          </div>
        ))}
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-24">
        <h2 className="text-xs font-semibold tracking-widest text-iron uppercase mb-6">
          Common questions
        </h2>
        <dl className="space-y-6">
          {FAQ.map((item) => (
            <div key={item.q} className="border-b border-iron/10 pb-6">
              <dt className="text-base font-semibold mb-2">{item.q}</dt>
              <dd className="text-sm text-iron leading-relaxed">{item.a}</dd>
            </div>
          ))}
        </dl>
      </section>

      <footer className="max-w-6xl mx-auto px-6 py-10 text-xs text-iron flex items-center justify-between border-t border-iron/10">
        <Link href={{ pathname: "/" }} className="hover:text-ink">
          ← Back to Helm
        </Link>
        <a href="mailto:hello@helm.app" className="hover:text-ink">
          hello@helm.app
        </a>
      </footer>
    </div>
  );
}
