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
          <h1 className="text-3xl font-semibold tracking-tight">Privacy policy</h1>
          <p className="text-sm text-iron mt-3 max-w-prose">
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
              <li key={s.name} className="flex justify-between gap-4 text-sm">
                <span className="font-medium text-ink">{s.name}</span>
                <span className="text-right">{s.role}</span>
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
            <a className="underline" href="mailto:privacy@helm.app">
              privacy@helm.app
            </a>{" "}
            for data requests;{" "}
            <a className="underline" href="mailto:hello@helm.app">
              hello@helm.app
            </a>{" "}
            for everything else.
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
      <Link href={{ pathname: "/terms" }} className="hover:text-ink">
        Terms
      </Link>
      <Link href={{ pathname: "/pricing" }} className="hover:text-ink">
        Pricing
      </Link>
    </footer>
  );
}
