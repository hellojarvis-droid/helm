"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/design/Icon";
import { cn } from "@/lib/cn";
import { listBusinesses, type Business } from "@/lib/api";

const BUSINESS_ID_RE = /^\/businesses\/([^/]+)/;
const STORAGE_KEY = "helm:active_business_id";

export function BusinessSwitcher() {
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Business[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [storedId, setStoredId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Hydrate the persisted selection on mount so navigating to non-business
  // routes (Today, Money, etc.) keeps showing the chosen business.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setStoredId(stored);
    } catch {
      // ignore storage access errors (private mode, etc.)
    }
  }, []);

  const urlId = useMemo(() => {
    const match = pathname.match(BUSINESS_ID_RE);
    const candidate = match?.[1];
    if (!candidate || candidate === "new") return null;
    return candidate;
  }, [pathname]);

  // When the URL is on a business detail, treat that as the active selection
  // and persist it.
  useEffect(() => {
    if (!urlId || urlId === storedId) return;
    setStoredId(urlId);
    try {
      window.localStorage.setItem(STORAGE_KEY, urlId);
    } catch {
      // ignore
    }
  }, [urlId, storedId]);

  const activeId = urlId ?? storedId;

  // If the persisted business no longer exists, clear it.
  useEffect(() => {
    if (!rows || !storedId) return;
    if (rows.some((b) => b.id === storedId)) return;
    setStoredId(null);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, [rows, storedId]);

  useEffect(() => {
    let cancelled = false;
    listBusinesses()
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const active = rows?.find((b) => b.id === activeId) ?? null;
  const label = active ? active.name : activeId ? "Loading…" : "All businesses";

  function pick(id: string) {
    setStoredId(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // ignore
    }
    setOpen(false);
    router.push(`/businesses/${id}`);
  }

  function clearActive() {
    setStoredId(null);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-paper border border-rule rounded-sm text-[13px] text-ink-2 hover:bg-sand max-w-[220px]"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Icon name="chart" size={13} className="opacity-70" />
        <span className="truncate font-medium text-ink">{label}</span>
        <Icon name="arrowDown" size={11} className="opacity-60 shrink-0" />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-full mt-1.5 w-72 rounded-md border border-rule bg-paper shadow-lg z-30 overflow-hidden"
        >
          <div className="px-3 pt-2.5 pb-1.5 text-[10px] font-medium uppercase tracking-[0.08em] text-ink-3">
            Switch business
          </div>
          <div className="max-h-72 overflow-y-auto">
            {error && <div className="px-3 py-2 text-[12px] text-rose-2">{error}</div>}
            {!error && rows === null && (
              <div className="px-3 py-2 text-[12px] text-ink-3">Loading…</div>
            )}
            {rows && rows.length === 0 && (
              <div className="px-3 py-2 text-[12px] text-ink-3">No businesses yet.</div>
            )}
            {rows && rows.length > 0 && (
              <button
                type="button"
                onClick={clearActive}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-sand transition-colors border-b border-rule",
                  activeId === null && "bg-sand",
                )}
                role="option"
                aria-selected={activeId === null}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium">All businesses</div>
                  <div className="text-[11px] text-ink-3">Portfolio view</div>
                </div>
                {activeId === null && <Icon name="check" size={13} className="text-ink-2" />}
              </button>
            )}
            {rows?.map((b) => {
              const isActive = b.id === activeId;
              return (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => pick(b.id)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-sand transition-colors",
                    isActive && "bg-sand",
                  )}
                  role="option"
                  aria-selected={isActive}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium truncate">{b.name}</div>
                    <div className="text-[11px] text-ink-3 truncate">
                      {prettyVertical(b.vertical)} · {b.status}
                    </div>
                  </div>
                  {isActive && <Icon name="check" size={13} className="text-ink-2" />}
                </button>
              );
            })}
          </div>
          <div className="border-t border-rule flex">
            <Link
              href="/businesses"
              onClick={() => setOpen(false)}
              className="flex-1 px-3 py-2 text-[12px] text-ink-2 hover:bg-sand inline-flex items-center gap-1.5"
            >
              <Icon name="folder" size={12} /> Manage all
            </Link>
            <Link
              href="/businesses/new"
              onClick={() => setOpen(false)}
              className="flex-1 px-3 py-2 text-[12px] text-ink-2 hover:bg-sand inline-flex items-center gap-1.5 border-l border-rule"
            >
              <Icon name="plus" size={12} /> New venture
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function prettyVertical(v: string) {
  const MAP: Record<string, string> = {
    dtc_physical: "DTC · physical",
    dtc_pod: "DTC · print-on-demand",
    saas: "SaaS",
    services: "Services",
  };
  return MAP[v] ?? v;
}
