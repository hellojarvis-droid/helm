import { LegalLayout, LegalSection } from "@/components/LegalLayout";

export const metadata = {
  title: "Terms of service — Helm",
  description: "The terms you agree to when using Helm.",
};

export default function TermsPage() {
  return (
    <LegalLayout slug="terms" title="Terms of service">
      <LegalSection title="What this is">
        <p>
          This page is a placeholder Terms of Service while we go through lawyer-reviewed final
          language. By using Helm before the formal terms ship, you agree to act in good faith and
          we agree to do the same. The final terms will replace this document and we&apos;ll surface
          the change in-app + by email.
        </p>
      </LegalSection>

      <LegalSection title="Helm in one paragraph">
        <p>
          Helm orchestrates AI agents that can act on your behalf — open Stripe accounts, run ads,
          reply to customers, and spend money up to the caps you set. You retain ownership of every
          business, every dollar earned, every connected account. We&apos;re the operator, not the
          principal.
        </p>
      </LegalSection>

      <LegalSection title="What you're responsible for">
        <ul className="list-disc list-inside space-y-2">
          <li>Accurate identity + payment information at sign-up.</li>
          <li>
            Compliance with the laws of every jurisdiction your businesses operate in — tax,
            advertising, consumer protection, data.
          </li>
          <li>Keeping your spend caps + MCC allowlists set to numbers you can absorb.</li>
          <li>Reading approval requests before tapping Approve.</li>
        </ul>
      </LegalSection>

      <LegalSection title="What we're responsible for">
        <ul className="list-disc list-inside space-y-2">
          <li>Honoring the kill switch within one second of every tap.</li>
          <li>Never spending past your caps. Stripe enforces this at the card level.</li>
          <li>Holding the audit trail. Every agent action is event-sourced + replayable.</li>
          <li>Telling you the truth about what the agents did.</li>
        </ul>
      </LegalSection>

      <LegalSection title="Disputes">
        <p>
          Email{" "}
          <a className="underline" href="mailto:hello@helm.app">
            hello@helm.app
          </a>
          . We&apos;d rather fix it than fight it.
        </p>
      </LegalSection>
    </LegalLayout>
  );
}
