"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import {
  getPublicStorefront,
  startPublicCheckout,
  type HelmProduct,
  type PublicStorefront,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ slug: string }>;
}

// Public customer-facing page. Deliberately outside the AppShell — no
// sidebar, no auth, no "helm" branding hammered in the customer's face.
// The business's own title/tagline get the hero slot.
export default function PublicStorefrontPage({ params }: PageProps) {
  const { slug } = use(params);
  return (
    <Suspense fallback={null}>
      <PublicStorefrontBody slug={slug} />
    </Suspense>
  );
}

function PublicStorefrontBody({ slug }: { slug: string }) {
  const searchParams = useSearchParams();
  const checkout = searchParams.get("checkout");

  const [storefront, setStorefront] = useState<PublicStorefront | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const sf = await getPublicStorefront(slug);
      setStorefront(sf);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="min-h-screen grid place-items-center bg-paper p-6">
        <div className="max-w-md text-center">
          <div className="font-serif text-[28px] mb-2">Storefront not found.</div>
          <p className="text-sm text-ink-3">
            The link might be wrong or the shop isn&apos;t live yet.
          </p>
        </div>
      </div>
    );
  }
  if (!storefront) {
    return (
      <div className="min-h-screen grid place-items-center bg-paper">
        <p className="text-sm text-ink-3">Loading…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper text-ink paper-grain">
      <Hero storefront={storefront} />
      <StatusBanner status={checkout} />
      <ProductGrid slug={storefront.slug} products={storefront.products} />
      <Footer businessName={storefront.business_name} />
    </div>
  );
}

function Hero({ storefront }: { storefront: PublicStorefront }) {
  return (
    <header className="max-w-4xl mx-auto px-6 pt-16 pb-12 text-center">
      <div className="text-[11px] text-ink-3 tracking-[0.12em] uppercase mb-4">
        {storefront.business_name}
      </div>
      <h1 className="font-serif text-5xl md:text-[64px] leading-[1.05] tracking-tightest mb-4">
        {storefront.title}
      </h1>
      {storefront.tagline && (
        <p className="text-[17px] text-ink-2 max-w-xl mx-auto leading-relaxed">
          {storefront.tagline}
        </p>
      )}
    </header>
  );
}

function StatusBanner({ status }: { status: string | null }) {
  if (status !== "success" && status !== "cancel") return null;
  const success = status === "success";
  return (
    <div className="max-w-4xl mx-auto px-6 mb-8">
      <div
        className={cn(
          "rounded-md border p-4 text-sm",
          success
            ? "border-sage/50 bg-sage-soft/50 text-sage-2"
            : "border-rule bg-paper-2 text-ink-2",
        )}
      >
        {success ? (
          <>
            <strong className="font-semibold">Thanks for ordering.</strong> Stripe confirmed
            your payment — you&apos;ll get a receipt by email shortly.
          </>
        ) : (
          <>
            Checkout was cancelled. No charge was made.
          </>
        )}
      </div>
    </div>
  );
}

function ProductGrid({
  slug,
  products,
}: {
  slug: string;
  products: HelmProduct[];
}) {
  if (products.length === 0) {
    return (
      <section className="max-w-4xl mx-auto px-6 py-10 text-center">
        <p className="text-sm text-ink-3">No products yet. Check back soon.</p>
      </section>
    );
  }
  return (
    <section className="max-w-5xl mx-auto px-6 pb-24 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {products.map((p) => (
        <ProductCard key={p.id} slug={slug} product={p} />
      ))}
    </section>
  );
}

function ProductCard({ slug, product }: { slug: string; product: HelmProduct }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function buy() {
    setBusy(true);
    setErr(null);
    try {
      const { url } = await startPublicCheckout(slug, product.id, 1);
      window.location.href = url;
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const outOfStock =
    product.inventory_qty !== null && product.inventory_qty <= 0;

  return (
    <div className="rounded-md border border-rule bg-paper overflow-hidden flex flex-col">
      <div className="aspect-square bg-sand border-b border-rule grid place-items-center overflow-hidden">
        {product.images[0] ? (
          <img
            src={product.images[0]}
            alt={product.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <Icon name="image" size={28} className="text-ink-3" />
        )}
      </div>
      <div className="p-5 flex flex-col gap-3 flex-1">
        <div>
          <h3 className="font-serif text-[22px] leading-tight tracking-[-0.01em]">
            {product.name}
          </h3>
          {product.description && (
            <p className="text-[13px] text-ink-2 leading-relaxed mt-2 line-clamp-3">
              {product.description}
            </p>
          )}
        </div>
        <div className="mt-auto flex items-baseline gap-2">
          <span className="font-serif text-[28px] tabular">
            ${(product.price_cents / 100).toFixed(2)}
          </span>
          {product.compare_at_price_cents && (
            <span className="text-[13px] line-through text-ink-3 tabular">
              ${(product.compare_at_price_cents / 100).toFixed(2)}
            </span>
          )}
        </div>
        {err && <p className="text-[12px] text-rose-2">{err}</p>}
        <button
          type="button"
          onClick={() => void buy()}
          disabled={busy || outOfStock}
          className={cn(
            "h-11 rounded-sm text-sm font-medium border transition-colors",
            outOfStock
              ? "bg-sand border-rule text-ink-3 cursor-not-allowed"
              : "bg-ink text-paper border-ink hover:bg-terracotta hover:border-terracotta",
          )}
        >
          {outOfStock ? "Sold out" : busy ? "Opening checkout…" : "Buy now"}
        </button>
      </div>
    </div>
  );
}

function Footer({ businessName }: { businessName: string }) {
  return (
    <footer className="max-w-5xl mx-auto px-6 py-10 text-[11px] text-ink-3 flex items-center justify-between border-t border-rule">
      <span>© {new Date().getFullYear()} {businessName}</span>
      <Link href="/" className="hover:text-ink">
        Powered by Helm
      </Link>
    </footer>
  );
}
