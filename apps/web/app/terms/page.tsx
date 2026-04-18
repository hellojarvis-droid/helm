import Link from "next/link";

export const metadata = {
  title: "Terms of service — Helm",
  description: "The terms you agree to when using Helm.",
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="flex items-center justify-between px-6 py-4 max-w-4xl mx-auto">
        <Link href={{ pathname: "/" }} className="text-lg font-semibold tracking-tight">
          Helm
        </Link>
        <Link href={{ pathname: "/sign-in" }} className="text-sm text-iron hover:text-ink">
          Sign in
        </Link>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        <header>
          <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-2">
            Legal · Last updated 2026-04-18
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Terms of service</h1>
        </header>

        <Section title="What this is">
          <p>
            This page is a placeholder Terms of Service while we go through lawyer-reviewed final
            language. By using Helm before the formal terms ship, you agree to act in good faith and
            we agree to do the same. The final terms will replace this document and we&apos;ll
            surface the change in-app + by email.
          </p>
        </Section>

        <Section title="Helm in one paragraph">
          <p>
            Helm orchestrates AI agents that can act on your behalf — open Stripe accounts, run ads,
            reply to customers, and spend money up to the caps you set. You retain ownership of
            every business, every dollar earned, every connected account. We&apos;re the operator,
            not the principal.
          </p>
        </Section>

        <Section title="What you're responsible for">
          <ul className="list-disc list-inside space-y-2">
            <li>Accurate identity + payment information at sign-up.</li>
            <li>
              Compliance with the laws of every jurisdiction your businesses operate in — tax,
              advertising, consumer protection, data.
            </li>
            <li>Keeping your spend caps + MCC allowlists set to numbers you can absorb.</li>
            <li>Reading approval requests before tapping Approve.</li>
          </ul>
        </Section>

        <Section title="What we're responsible for">
          <ul className="list-disc list-inside space-y-2">
            <li>Honoring the kill switch within one second of every tap.</li>
            <li>Never spending past your caps. Stripe enforces this at the card level.</li>
            <li>Holding the audit trail. Every agent action is event-sourced + replayable.</li>
            <li>Telling you the truth about what the agents did.</li>
          </ul>
        </Section>

        <Section title="Disputes">
          <p>
            Email{" "}
            <a className="underline" href="mailto:hello@helm.app">
              hello@helm.app
            </a>
            . We&apos;d rather fix it than fight it.
          </p>
        </Section>

        <Footer />
      </main>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold mb-3">{title}</h2>
      <div className="text-sm leading-relaxed text-iron space-y-3">{children}</div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="pt-10 mt-10 border-t border-iron/10 text-xs text-iron flex gap-4">
      <Link href={{ pathname: "/" }} className="hover:text-ink">
        ← Helm
      </Link>
      <Link href={{ pathname: "/privacy" }} className="hover:text-ink">
        Privacy
      </Link>
      <Link href={{ pathname: "/pricing" }} className="hover:text-ink">
        Pricing
      </Link>
    </footer>
  );
}
