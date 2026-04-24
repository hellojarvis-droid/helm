import Link from "next/link";

export const metadata = {
  title: "Privacy — Helm",
  description: "What data Helm collects, why, and who else touches it.",
};

const SUBPROCESSORS = [
  { name: "Supabase", role: "Auth + Postgres + storage" },
  { name: "Anthropic", role: "LLM inference (CEO Agent + every specialist)" },
  { name: "OpenAI", role: "Whisper transcription for the mobile mic button" },
  { name: "Composio", role: "OAuth + tool execution into 3rd-party apps you connect" },
  { name: "Stripe", role: "Payments, Connect, Issuing, Billing" },
  { name: "Render", role: "API hosting" },
  { name: "Vercel", role: "Web hosting" },
  { name: "Sentry", role: "Error monitoring (no PII; trace IDs only)" },
  { name: "Langfuse", role: "LLM trace + cost analytics" },
  { name: "PostHog", role: "Product analytics (page views, feature adoption)" },
  { name: "Expo", role: "Mobile push notification routing" },
];

export default function PrivacyPage() {
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
            Privacy policy
          </h1>
          <p className="text-sm text-ink-2 mt-4 max-w-prose leading-relaxed">
            What we collect, why, who else touches it. Plain English. The lawyer-reviewed formal
            policy lands before public launch and replaces this document.
          </p>
        </header>

        <Section title="Identity">
          <p>
            We collect your email + a Supabase-issued user ID. That&apos;s our handle on you. Email
            is used for auth, billing receipts via Stripe, and product correspondence we&apos;d send
            anyway. We do not sell email addresses. We do not run a marketing email program.
          </p>
        </Section>

        <Section title="What you tell us by using Helm">
          <ul className="list-disc list-inside space-y-2">
            <li>
              Chat messages, including any business context you share. We pass these to Anthropic +
              OpenAI to do their job, and store them in the agent event log so you can replay any
              decision.
            </li>
            <li>Business names, verticals, brand kits, integration tokens (Composio-mediated).</li>
            <li>
              Spend events: every Stripe Issuing card authorization, the merchant, the amount, the
              decision (approved/declined and why).
            </li>
          </ul>
        </Section>

        <Section title="What you don't give us">
          <ul className="list-disc list-inside space-y-2">
            <li>
              Raw OAuth credentials for Gmail/Slack/etc. Composio holds those; we ask for ephemeral
              tokens scoped to the action.
            </li>
            <li>
              Stripe payment method details. Stripe holds those; we hold a customer ID pointer.
            </li>
            <li>
              Your phone&apos;s contacts, photos, location, or microphone audio (we transcribe and
              discard).
            </li>
          </ul>
        </Section>

        <Section title="Subprocessors">
          <p>
            The following services touch your data on our behalf. Email us if any are dealbreakers.
          </p>
          <ul className="space-y-1 mt-3">
            {SUBPROCESSORS.map((s) => (
              <li
                key={s.name}
                className="flex justify-between gap-4 text-sm py-2 border-b border-rule last:border-b-0"
              >
                <span className="font-medium text-ink">{s.name}</span>
                <span className="text-right text-ink-2">{s.role}</span>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="How long we keep it">
          <p>
            Live for the lifetime of your account + 30 days post-cancellation so you can export.
            After that, it&apos;s deleted. Aggregated, anonymous metrics may persist for product
            analytics.
          </p>
        </Section>

        <Section title="Your controls">
          <ul className="list-disc list-inside space-y-2">
            <li>Export every record we hold on you on request.</li>
            <li>Delete your account on request — settled out within 7 days.</li>
            <li>Stripe Customer Portal for everything subscription-side.</li>
            <li>The Safety tab&apos;s kill switch halts every running agent in &lt;1s.</li>
          </ul>
        </Section>

        <Section title="Contact">
          <p>
            <a
              className="underline text-terracotta-2 hover:text-terracotta"
              href="mailto:privacy@helm.app"
            >
              privacy@helm.app
            </a>{" "}
            for data requests;{" "}
            <a
              className="underline text-terracotta-2 hover:text-terracotta"
              href="mailto:hello@helm.app"
            >
              hello@helm.app
            </a>{" "}
            for everything else.
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
      <Link href="/terms" className="hover:text-ink">
        Terms
      </Link>
      <Link href="/pricing" className="hover:text-ink">
        Pricing
      </Link>
    </footer>
  );
}
