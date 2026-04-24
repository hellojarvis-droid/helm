"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { AppShell } from "@/components/AppShell";
import { cn } from "@/lib/cn";
import { listBusinesses, type Business } from "@/lib/api";

// Warm-paper shell. Left sidebar with 8 clusters per the Creative
// Studio research (Higgsfield → Krea pattern). Any tool route renders
// as children; this layout owns business selection + sidebar state.

interface Cluster {
  label: string;
  href: string;
  glyph: string;
  group: "generate" | "manage" | "publish";
}

const CLUSTERS: Cluster[] = [
  { label: "Home", href: "/studio", glyph: "⌂", group: "generate" },
  { label: "Image", href: "/studio/image", glyph: "▢", group: "generate" },
  { label: "Video", href: "/studio/video", glyph: "▷", group: "generate" },
  { label: "Edit", href: "/studio/edit", glyph: "✎", group: "generate" },
  { label: "Enhance", href: "/studio/enhance", glyph: "✦", group: "generate" },
  { label: "Lipsync", href: "/studio/lipsync", glyph: "♪", group: "generate" },
  { label: "Marketing", href: "/studio/marketing", glyph: "◎", group: "publish" },
  { label: "Library", href: "/studio/library", glyph: "☐", group: "manage" },
];

const STUDIO_BUSINESS_KEY = "helm:studio:business";

export default function StudioLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(
    typeof window === "undefined" ? false : window.innerWidth < 900,
  );
  useEffect(() => {
    const handler = () => {
      if (typeof window === "undefined") return;
      if (window.innerWidth < 900) setCollapsed(true);
    };
    if (typeof window !== "undefined") {
      window.addEventListener("resize", handler);
      return () => window.removeEventListener("resize", handler);
    }
    return undefined;
  }, []);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [businessId, setBusinessIdRaw] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const rows = await listBusinesses();
        setBusinesses(rows);
        const saved =
          typeof window !== "undefined"
            ? window.localStorage.getItem(STUDIO_BUSINESS_KEY)
            : null;
        if (saved && rows.some((r) => r.id === saved)) {
          setBusinessIdRaw(saved);
        } else if (rows[0]) {
          setBusinessIdRaw(rows[0].id);
        }
      } catch {
        // swallow — unauth view hides the picker
      }
    })();
  }, []);

  const setBusinessId = (id: string | null) => {
    setBusinessIdRaw(id);
    if (typeof window !== "undefined") {
      if (id) window.localStorage.setItem(STUDIO_BUSINESS_KEY, id);
      else window.localStorage.removeItem(STUDIO_BUSINESS_KEY);
    }
  };

  return (
    <AppShell>
      <StudioContext.Provider
        value={{
          businessId,
          businesses,
          setBusinessId,
        }}
      >
        <div className="flex h-[calc(100vh-60px)]">
          <aside
            className={cn(
              "shrink-0 border-r border-rule bg-paper-2 transition-[width] duration-200",
              collapsed ? "w-[56px]" : "w-[220px]",
            )}
          >
            <div className="p-3 flex items-center justify-between">
              {!collapsed && (
                <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
                  Studio
                </div>
              )}
              <button
                type="button"
                onClick={() => setCollapsed((v) => !v)}
                className="text-[11px] text-ink-3 hover:text-ink"
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {collapsed ? "›" : "‹"}
              </button>
            </div>

            {!collapsed && businesses.length > 0 && (
              <div className="px-3 pb-3">
                <div className="text-[10px] uppercase tracking-[0.06em] text-ink-3 mb-1">
                  Business
                </div>
                <select
                  value={businessId ?? ""}
                  onChange={(e) => setBusinessId(e.target.value || null)}
                  className="w-full rounded-sm border border-rule bg-paper px-2 py-1.5 text-[12px]"
                >
                  <option value="">—</option>
                  {businesses.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <NavGroup
              label="Generate"
              show={!collapsed}
              items={CLUSTERS.filter((c) => c.group === "generate")}
              pathname={pathname}
              collapsed={collapsed}
            />
            <NavGroup
              label="Publish"
              show={!collapsed}
              items={CLUSTERS.filter((c) => c.group === "publish")}
              pathname={pathname}
              collapsed={collapsed}
            />
            <NavGroup
              label="Manage"
              show={!collapsed}
              items={CLUSTERS.filter((c) => c.group === "manage")}
              pathname={pathname}
              collapsed={collapsed}
            />

            {!collapsed && (
              <div className="mt-auto px-3 py-3 border-t border-rule space-y-0.5">
                <Link
                  href="/studio/compare"
                  className={cn(
                    "block rounded-sm px-2 py-1.5 text-[12px]",
                    pathname === "/studio/compare"
                      ? "bg-paper border border-ink text-ink"
                      : "text-ink-2 hover:bg-sand",
                  )}
                >
                  Compare models
                </Link>
                <Link
                  href="/studio/usage"
                  className={cn(
                    "block rounded-sm px-2 py-1.5 text-[12px]",
                    pathname === "/studio/usage"
                      ? "bg-paper border border-ink text-ink"
                      : "text-ink-2 hover:bg-sand",
                  )}
                >
                  Usage &amp; receipts
                </Link>
                <Link
                  href="/studio/raw"
                  className="block rounded-sm px-2 py-1.5 text-[11px] text-ink-3 hover:text-ink"
                >
                  Raw render tools →
                </Link>
              </div>
            )}
          </aside>

          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      </StudioContext.Provider>
    </AppShell>
  );
}

function NavGroup({
  label,
  show,
  items,
  pathname,
  collapsed,
}: {
  label: string;
  show: boolean;
  items: Cluster[];
  pathname: string;
  collapsed: boolean;
}) {
  return (
    <div className="mb-3">
      {show && (
        <div className="px-3 text-[10px] uppercase tracking-[0.06em] text-ink-3 mb-1">
          {label}
        </div>
      )}
      <ul>
        {items.map((c) => {
          const active =
            c.href === "/studio"
              ? pathname === "/studio"
              : pathname === c.href || pathname.startsWith(c.href + "/");
          return (
            <li key={c.href}>
              <Link
                href={c.href}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 text-[13px]",
                  active
                    ? "bg-paper border-l-2 border-terracotta text-ink"
                    : "text-ink-2 hover:bg-sand border-l-2 border-transparent",
                )}
                title={c.label}
              >
                <span
                  className={cn(
                    "inline-flex h-5 w-5 items-center justify-center text-ink-3",
                    active && "text-terracotta",
                  )}
                  aria-hidden
                >
                  {c.glyph}
                </span>
                {!collapsed && <span>{c.label}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Shared Studio context so every tool page can grab selected business.
// ─────────────────────────────────────────────────────────────

export interface StudioCtx {
  businessId: string | null;
  businesses: Business[];
  setBusinessId: (id: string | null) => void;
}

const StudioContext = createContext<StudioCtx>({
  businessId: null,
  businesses: [],
  setBusinessId: () => {},
});

export function useStudio(): StudioCtx {
  return useContext(StudioContext);
}
