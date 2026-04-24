import Link from "next/link";

export const metadata = {
  title: "Terms of service — Helm",
  description: "The terms you agree to when using Helm.",
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-paper text-ink paper-grain">
      <header className="flex items-center justify-between px-8 py-5 max-w-4xl mx-auto">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="h-8 w-8 grid place-items-center rounded-md bg-ink text-paper font-serif text-[22px] leading-none">
            H
          </div>
          <span className="text-[18px] font-semibold tracking-tight">Helm</span>
        </Link>
        <Link href="/sign-in" className="text-sm text-ink-2 hover:text-ink">
          Sign in
        </Link>
      </header>

      <main className="max-w-3xl mx-auto px-8 py-14 space-y-10">
        <header>
          <div className="text-[11px] font-medium tracking-[0.08em] text-ink-3 uppercase mb-3">
            Legal · Last updated 2026-04-18
          </div>
          <h1 className="font-serif text-[44px] leading-tight tracking-tightest">
            Terms of service
          </h1>
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
            <a className="underline text-terracotta-2 hover:text-terracotta" href="mailto:hello@helm.app">
              hello@helm.app
            </a>
            . We&apos;d rather fix it than fight it.
          </p>
        </Section>

        <FooterLinks />
      </main>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold mb-3">{title}</h2>
      <div className="text-sm leading-relaxed text-ink-2 space-y-3">{children}</div>
    </section>
  );
}

function FooterLinks() {
  return (
    <footer className="pt-10 mt-10 border-t border-rule text-xs text-ink-3 flex gap-4">
      <Link href="/" className="hover:text-ink">
        ← Helm
      </Link>
      <Link href="/privacy" className="hover:text-ink">
        Privacy
      </Link>
      <Link href="/pricing" className="hover:text-ink">
        Pricing
      </Link>
    </footer>
  );
}
