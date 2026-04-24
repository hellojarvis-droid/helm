"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { RenderPicker } from "@/components/storefront/RenderPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  createProduct,
  deleteProduct,
  getBusiness,
  getStorefront,
  listProducts,
  updateProduct,
  upsertStorefront,
  type BusinessDetail,
  type HelmProduct,
  type HelmStorefront,
} from "@/lib/api";
import { clientEnv } from "@/lib/env";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function StorefrontAdminPage({ params }: PageProps) {
  const { id } = use(params);
  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [storefront, setStorefront] = useState<HelmStorefront | null>(null);
  const [products, setProducts] = useState<HelmProduct[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [tagline, setTagline] = useState("");
  const [published, setPublished] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [b, sf, prods] = await Promise.all([
        getBusiness(id),
        getStorefront(id),
        listProducts(id),
      ]);
      setBiz(b);
      setStorefront(sf);
      setProducts(prods);
      if (sf) {
        setSlug(sf.slug);
        setTitle(sf.title);
        setTagline(sf.tagline ?? "");
        setPublished(sf.published);
      } else {
        setSlug(defaultSlug(b.name));
        setTitle(b.name);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveStorefront(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const sf = await upsertStorefront(id, {
        slug: slug.toLowerCase().trim(),
        title: title.trim(),
        tagline: tagline.trim() || null,
        published,
      });
      setStorefront(sf);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onCreateProduct(body: Parameters<typeof createProduct>[1]) {
    setError(null);
    try {
      await createProduct(id, body);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onPatchProduct(
    productId: string,
    body: Parameters<typeof updateProduct>[2],
  ) {
    setError(null);
    try {
      await updateProduct(id, productId, body);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onDeleteProduct(productId: string) {
    if (!confirm("Delete this product? This can't be undone.")) return;
    setError(null);
    try {
      await deleteProduct(id, productId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const publicUrl = storefront
    ? publicStorefrontUrl(storefront.slug)
    : null;

  return (
    <AppShell breadcrumbs={["Helm", "Businesses", biz?.name ?? "Business", "Storefront"]}>
      <div className="px-10 pt-8 pb-20 max-w-5xl">
        <header className="mb-7 flex items-end justify-between">
          <div>
            <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">
              {biz?.name ?? "Business"} · storefront
            </div>
            <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
              Helm Storefront
            </h1>
            <p className="text-sm text-ink-3 max-w-prose">
              A first-party checkout page for customers — served at{" "}
              <span className="font-mono text-ink">helm.app/s/your-slug</span>. Money lands
              directly on this business&apos;s Stripe Connect account.
            </p>
          </div>
          {publicUrl && storefront?.published && (
            <a
              href={publicUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 px-3.5 h-9 text-[13px] rounded-sm border border-rule bg-paper hover:bg-sand text-ink"
            >
              Visit storefront ↗
            </a>
          )}
        </header>

        {error && (
          <div className="mb-5 rounded-md border border-rose-2/50 bg-rose-soft/50 p-4 text-sm text-rose-2">
            {error}
          </div>
        )}

        <div className="grid grid-cols-12 gap-5 mb-8">
          <form
            onSubmit={saveStorefront}
            className="col-span-7 rounded-md border border-rule bg-paper p-[22px] space-y-4"
          >
            <div className="text-[13px] font-medium text-ink-2 flex items-center justify-between">
              Storefront settings
              {storefront && (
                <span className={cn("chip", storefront.published ? "chip-sage" : "")}>
                  {storefront.published ? "published" : "draft"}
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
                Slug — the URL suffix at helm.app/s/
              </label>
              <Input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="olivine-goods"
                minLength={2}
                maxLength={64}
                required
              />
              <p className="text-[11px] text-ink-3 font-mono">
                {clientEnv().NEXT_PUBLIC_HELM_API_BASE
                  ? `${webOriginFallback()}/s/${slug || "…"}`
                  : `helm.app/s/${slug || "…"}`}
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
                Title
              </label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={biz?.name ?? "Your brand"}
                maxLength={160}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
                Tagline (optional)
              </label>
              <Input
                value={tagline}
                onChange={(e) => setTagline(e.target.value)}
                placeholder="Minimalist home goods in natural linen."
                maxLength={280}
              />
            </div>
            <label className="flex items-center gap-2.5 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={published}
                onChange={(e) => setPublished(e.target.checked)}
                className="accent-terracotta"
              />
              Publish — make the page live at the slug URL.
            </label>
            <p className="text-[11.5px] text-ink-3 leading-relaxed">
              Unpublished storefronts 404 for visitors even if they guess the slug — useful
              for staging before you link it anywhere.
            </p>
            <div className="flex gap-2 pt-2">
              <Button type="submit" variant="accent" disabled={busy}>
                {busy ? "Saving…" : storefront ? "Save changes" : "Create storefront"}
              </Button>
              {!biz?.stripe_onboarding_complete && published && (
                <span className="text-[11.5px] text-amber-2 self-center">
                  Note: Stripe onboarding isn&apos;t complete — checkout will fail until it is.
                </span>
              )}
            </div>
          </form>

          <div className="col-span-5 rounded-md border border-rule bg-paper-2 p-[22px] text-[13px] text-ink-2 leading-relaxed space-y-3">
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3">
              How money flows
            </div>
            <p>
              Customer pays via Stripe Checkout (hosted by Stripe). The payment lands on your
              business&apos;s connected Stripe account — Helm is not in the money path and
              takes no platform fee.
            </p>
            <p>
              A <span className="font-mono">payment_intent.succeeded</span> webhook fires back
              to Helm and gets logged as a revenue event in{" "}
              <Link href="/events" className="text-terracotta-2 hover:underline">
                /events
              </Link>
              .
            </p>
            <p>
              Customers don&apos;t sign in. The Helm Storefront URL is public the moment you
              check Publish.
            </p>
          </div>
        </div>

        <section>
          <div className="flex items-end justify-between mb-4">
            <div>
              <h2 className="text-[13px] font-medium text-ink-2 uppercase tracking-[0.08em]">
                Products
              </h2>
              <p className="text-[12px] text-ink-3">
                {products.length} total · {products.filter((p) => p.published).length}{" "}
                published
              </p>
            </div>
          </div>
          <NewProductForm onCreate={onCreateProduct} />
          {products.length === 0 ? (
            <p className="text-sm text-ink-3 mt-4 p-6 rounded-md border border-rule bg-paper">
              No products yet. Add your first SKU above.
            </p>
          ) : (
            <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
              {products.map((p) => (
                <ProductCard
                  key={p.id}
                  product={p}
                  businessId={id}
                  onPatch={(body) => onPatchProduct(p.id, body)}
                  onDelete={() => onDeleteProduct(p.id)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function NewProductForm({
  onCreate,
}: {
  onCreate: (body: Parameters<typeof createProduct>[1]) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [priceDollars, setPriceDollars] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !priceDollars.trim()) return;
    const cents = Math.round(parseFloat(priceDollars) * 100);
    if (!Number.isFinite(cents) || cents < 0) return;
    setBusy(true);
    try {
      await onCreate({
        name: name.trim(),
        description: description.trim() || null,
        price_cents: cents,
        published: false,
      });
      setName("");
      setPriceDollars("");
      setDescription("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-md border border-rule bg-paper p-[18px] grid grid-cols-12 gap-3 items-end"
    >
      <div className="col-span-5 space-y-1">
        <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
          Product name
        </label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Linen Tote, 100% flax"
          required
        />
      </div>
      <div className="col-span-2 space-y-1">
        <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
          Price (USD)
        </label>
        <Input
          value={priceDollars}
          onChange={(e) => setPriceDollars(e.target.value)}
          placeholder="68.00"
          type="number"
          min={0}
          step="0.01"
          required
        />
      </div>
      <div className="col-span-3 space-y-1">
        <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
          Description (optional)
        </label>
        <Input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Short description shown on the checkout page"
        />
      </div>
      <div className="col-span-2">
        <Button type="submit" variant="accent" className="w-full" disabled={busy}>
          {busy ? "Adding…" : "Add product"}
        </Button>
      </div>
    </form>
  );
}

function ProductCard({
  product,
  businessId,
  onPatch,
  onDelete,
}: {
  product: HelmProduct;
  businessId: string;
  onPatch: (body: Partial<Parameters<typeof createProduct>[1]>) => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(product.name);
  const [priceDollars, setPriceDollars] = useState((product.price_cents / 100).toFixed(2));
  const [description, setDescription] = useState(product.description ?? "");
  const [inventory, setInventory] = useState(
    product.inventory_qty === null ? "" : String(product.inventory_qty),
  );
  const [imageUrl, setImageUrl] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);

  async function save() {
    const cents = Math.round(parseFloat(priceDollars) * 100);
    if (!Number.isFinite(cents)) return;
    await onPatch({
      name: name.trim(),
      description: description.trim() || null,
      price_cents: cents,
      inventory_qty: inventory.trim() ? Number(inventory) : null,
    });
    setEditing(false);
  }

  async function togglePublish() {
    await onPatch({ published: !product.published });
  }

  async function addImage(e: React.FormEvent) {
    e.preventDefault();
    if (!imageUrl.trim()) return;
    const images = [...product.images, imageUrl.trim()];
    await onPatch({ images });
    setImageUrl("");
  }

  async function removeImage(url: string) {
    const images = product.images.filter((u) => u !== url);
    await onPatch({ images });
  }

  return (
    <div className="rounded-md border border-rule bg-paper p-4">
      <div className="flex items-start gap-3">
        <div className="h-16 w-16 rounded-sm bg-sand border border-rule grid place-items-center overflow-hidden shrink-0">
          {product.images[0] ? (
            <img
              src={product.images[0]}
              alt={product.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <Icon name="image" size={20} className="text-ink-3" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-medium truncate">{product.name}</span>
            <span className={cn("chip", product.published ? "chip-sage" : "")}>
              {product.published ? "live" : "draft"}
            </span>
          </div>
          <div className="text-[11px] text-ink-3 font-mono mt-0.5">
            ${(product.price_cents / 100).toFixed(2)} · {product.currency.toUpperCase()}
            {product.inventory_qty !== null && ` · ${product.inventory_qty} in stock`}
            {product.images.length > 0 && ` · ${product.images.length} image${product.images.length === 1 ? "" : "s"}`}
          </div>
          {product.description && !editing && (
            <p className="text-[12.5px] text-ink-2 mt-2 leading-relaxed line-clamp-2">
              {product.description}
            </p>
          )}
        </div>
      </div>

      {editing && (
        <div className="mt-4 space-y-3 pt-3 border-t border-rule">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
          <div className="grid grid-cols-2 gap-3">
            <Input
              value={priceDollars}
              onChange={(e) => setPriceDollars(e.target.value)}
              placeholder="Price"
              type="number"
              min={0}
              step="0.01"
            />
            <Input
              value={inventory}
              onChange={(e) => setInventory(e.target.value)}
              placeholder="Inventory (blank = unlimited)"
              type="number"
              min={0}
            />
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Description"
            className="w-full rounded-sm border border-rule bg-paper px-3 py-2 text-[13.5px] text-ink resize-none focus:outline-none focus:border-ink-2"
          />
          <div className="space-y-2">
            <form onSubmit={addImage} className="flex gap-2">
              <Input
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                placeholder="Image URL"
                type="url"
              />
              <Button type="submit" variant="outline" size="sm">
                Add URL
              </Button>
              <Button
                type="button"
                variant="accent"
                size="sm"
                onClick={() => setPickerOpen(true)}
              >
                <Icon name="sparkle" size={12} /> From Studio
              </Button>
            </form>
            <RenderPicker
              open={pickerOpen}
              onClose={() => setPickerOpen(false)}
              businessId={businessId}
              onPick={(url) => {
                const images = [...product.images, url];
                void onPatch({ images });
              }}
            />
          </div>
          {product.images.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {product.images.map((u) => (
                <button
                  key={u}
                  type="button"
                  onClick={() => void removeImage(u)}
                  className="relative h-14 w-14 rounded-sm border border-rule overflow-hidden group"
                  title="Click to remove"
                >
                  <img src={u} alt="" className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-ink/50 opacity-0 group-hover:opacity-100 grid place-items-center text-paper text-[10px]">
                    Remove
                  </div>
                </button>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <Button type="button" variant="accent" size="sm" onClick={() => void save()}>
              Save
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setEditing(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {!editing && (
        <div className="mt-3 pt-3 border-t border-rule flex items-center justify-between text-[12px]">
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void togglePublish()}
              className="text-terracotta-2 hover:underline"
            >
              {product.published ? "Unpublish" : "Publish"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-ink-3 hover:text-ink"
            >
              Edit
            </button>
          </div>
          <button
            type="button"
            onClick={onDelete}
            className="text-ink-3 hover:text-rose-2"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function defaultSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function webOriginFallback(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}

function publicStorefrontUrl(slug: string): string {
  return `${webOriginFallback()}/s/${slug}`;
}
