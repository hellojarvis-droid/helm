import Link from "next/link";

type Slug = "privacy" | "terms";

const OTHER_LEGAL: Record<Slug, { href: string; label: string }> = {
  privacy: { href: "/terms", label: "Terms" },
  terms: { href: "/privacy", label: "Privacy" },
};

export function LegalLayout({
  slug,
  title,
  intro,
  children,
}: {
  slug: Slug;
  title: string;
  intro?: React.ReactNode;
  children: React.ReactNode;
}) {
  const other = OTHER_LEGAL[slug];
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
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          {intro ? <p className="text-sm text-iron mt-3 max-w-prose">{intro}</p> : null}
        </header>

        {children}

        <footer className="pt-10 mt-10 border-t border-iron/10 text-xs text-iron flex gap-4">
          <Link href={{ pathname: "/" }} className="hover:text-ink">
            ← Helm
          </Link>
          <Link href={{ pathname: other.href }} className="hover:text-ink">
            {other.label}
          </Link>
          <Link href={{ pathname: "/pricing" }} className="hover:text-ink">
            Pricing
          </Link>
        </footer>
      </main>
    </div>
  );
}

export function LegalSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold mb-3">{title}</h2>
      <div className="text-sm leading-relaxed text-iron space-y-3">{children}</div>
    </section>
  );
}
