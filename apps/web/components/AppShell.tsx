"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AtlasDock } from "@/components/chat/AtlasDock";
import { BalanceChip } from "@/components/credits/BalanceChip";
import { BusinessSwitcher } from "@/components/BusinessSwitcher";
import { Icon, type IconName } from "@/components/design/Icon";
import { KillSwitchBanner } from "@/components/KillSwitchBanner";
import { cn } from "@/lib/cn";
import { supabaseBrowser } from "@/lib/supabase/client";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  dot?: "terracotta" | "amber";
}

const NAV: NavItem[] = [
  { href: "/today", label: "Today", icon: "home" },
  { href: "/money", label: "Money", icon: "receipt" },
  { href: "/approvals", label: "Approvals", icon: "check", dot: "terracotta" },
  { href: "/builder", label: "Builder", icon: "folder" },
  { href: "/studio", label: "Creative Studio", icon: "video" },
  { href: "/agents", label: "Agents", icon: "users" },
  { href: "/connections", label: "Connections", icon: "tweaks" },
  { href: "/safety", label: "Safety", icon: "shield" },
  { href: "/billing", label: "Billing", icon: "card" },
];

export interface AppShellProps {
  children: React.ReactNode;
  breadcrumbs?: string[];
  userEmail?: string | null;
}

export function AppShell({ children, breadcrumbs, userEmail }: AppShellProps) {
  const pathname = usePathname();
  const onChatRoute = pathname?.startsWith("/chat") ?? false;
  const crumbs = breadcrumbs ?? deriveCrumbs(pathname ?? "");
  const initials = initialsFrom(userEmail);
  const contextKey = contextFromPath(pathname ?? "");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="min-h-screen bg-paper text-ink lg:grid lg:grid-cols-[248px_1fr]">
      <Sidebar pathname={pathname ?? ""} initials={initials} className="hidden lg:flex" />
      {mobileNavOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink/35 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        >
          <Sidebar
            pathname={pathname ?? ""}
            initials={initials}
            className="h-full w-[min(86vw,280px)]"
            onNavigate={() => setMobileNavOpen(false)}
          />
        </div>
      )}
      <div className="flex flex-col min-h-screen overflow-hidden">
        <KillSwitchBanner />
        <Topbar
          crumbs={crumbs}
          initials={initials}
          onOpenNav={() => setMobileNavOpen(true)}
          onOpenCommand={() => setCommandOpen(true)}
        />
        <main className="flex-1 overflow-y-auto scroll-paper paper-grain">{children}</main>
      </div>
      {!onChatRoute && <AtlasDock contextKey={contextKey} />}
      {commandOpen && (
        <CommandPalette pathname={pathname ?? ""} onClose={() => setCommandOpen(false)} />
      )}
    </div>
  );
}

function Sidebar({
  pathname,
  initials,
  className,
  onNavigate,
}: {
  pathname: string;
  initials: string;
  className?: string;
  onNavigate?: () => void;
}) {
  const router = useRouter();

  async function signOut() {
    const supabase = supabaseBrowser();
    await supabase.auth.signOut();
    router.replace("/sign-in");
    router.refresh();
  }

  return (
    <aside
      className={cn(
        "bg-paper-2 border-r border-rule flex flex-col gap-5 px-4 py-5 overflow-hidden",
        className,
      )}
      onClick={(event) => event.stopPropagation()}
    >
      <Link
        href="/today"
        className="flex items-center gap-2.5 px-1.5 py-1 hover:opacity-90"
        onClick={onNavigate}
      >
        <div className="h-7 w-7 grid place-items-center rounded-md bg-ink text-paper font-serif text-[20px] leading-none">
          H
        </div>
        <div>
          <div className="text-[17px] font-semibold tracking-tight leading-none">Helm</div>
          <div className="text-[11px] text-ink-3 tracking-[0.04em] uppercase mt-1">
            Your holdings
          </div>
        </div>
      </Link>

      <nav className="flex flex-col gap-0.5">
        {NAV.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[14px] transition-colors",
                active ? "bg-ink text-paper" : "text-ink-2 hover:bg-sand hover:text-ink",
              )}
            >
              <Icon name={item.icon} size={16} className="opacity-80" />
              <span className="flex-1">{item.label}</span>
              {item.dot && (
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    item.dot === "terracotta" ? "bg-terracotta" : "bg-amber",
                  )}
                />
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto flex flex-col gap-2">
        <Link
          href="/chat"
          onClick={onNavigate}
          className="flex items-center gap-2.5 rounded-md border border-rule bg-paper p-2.5 hover:bg-sand transition-colors"
        >
          <div className="relative h-8 w-8 grid place-items-center rounded-full bg-gradient-to-br from-terracotta to-amber text-paper font-serif text-base">
            A
            <span className="absolute -right-0.5 -bottom-0.5 h-2.5 w-2.5 rounded-full bg-sage border-2 border-paper-2" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium leading-tight">Ask Atlas</div>
            <div className="text-[11px] text-ink-3">CEO Agent · online</div>
          </div>
          <Icon name="sparkle" size={14} />
        </Link>
        <Link
          href="/events"
          onClick={onNavigate}
          className={cn(
            "flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[13px] transition-colors",
            isActive(pathname, "/events")
              ? "bg-ink text-paper"
              : "text-ink-2 hover:bg-sand hover:text-ink",
          )}
        >
          <Icon name="book" size={15} className="opacity-80" />
          <span className="flex-1">Logs</span>
        </Link>
        <button
          onClick={signOut}
          className="text-[12px] text-ink-3 hover:text-ink text-left px-2.5 py-1"
        >
          Sign out · {initials}
        </button>
      </div>
    </aside>
  );
}

function Topbar({
  crumbs,
  initials,
  onOpenNav,
  onOpenCommand,
}: {
  crumbs: string[];
  initials: string;
  onOpenNav: () => void;
  onOpenCommand: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3.5 border-b border-rule bg-paper sm:px-7">
      <button
        type="button"
        onClick={onOpenNav}
        className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-rule bg-paper text-ink-2 hover:bg-sand lg:hidden"
        aria-label="Open navigation"
      >
        <Icon name="menu" size={15} />
      </button>
      <div className="hidden min-w-0 sm:block">
        <BusinessSwitcher />
      </div>
      <div className="min-w-0 truncate text-[13px] text-ink-3">
        {crumbs.map((c, i) => (
          <span key={i}>
            {i > 0 && <span className="mx-2 opacity-50">/</span>}
            {i === crumbs.length - 1 ? (
              <b className="text-ink font-medium">{c}</b>
            ) : (
              <span>{c}</span>
            )}
          </span>
        ))}
      </div>
      <div className="flex-1" />
      <Link
        href="/onboarding"
        className="hidden items-center gap-1.5 px-3 py-1.5 bg-paper border border-rule rounded-sm text-[13px] text-ink-2 hover:bg-sand sm:inline-flex"
      >
        <Icon name="sparkle" size={13} /> New venture
      </Link>
      <button
        type="button"
        onClick={onOpenCommand}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-paper border border-rule rounded-sm text-[13px] text-ink-2 hover:bg-sand"
        aria-label="Search"
      >
        <Icon name="search" size={13} />
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden sm:inline">⌘K</kbd>
      </button>
      <Link
        href="/approvals"
        aria-label="Notifications"
        className="inline-flex items-center px-2.5 py-1.5 bg-paper border border-rule rounded-sm text-ink-2 hover:bg-sand"
      >
        <Icon name="bell" size={13} />
      </Link>
      <div className="hidden md:block">
        <BalanceChip />
      </div>
      <div className="hidden h-8 w-8 rounded-full bg-sand-2 place-items-center text-xs font-medium text-ink-2 border border-rule sm:grid">
        {initials}
      </div>
    </div>
  );
}

function CommandPalette({ pathname, onClose }: { pathname: string; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const actions = useMemo(
    () => [
      { href: "/chat", label: "Ask Atlas", icon: "sparkle" as IconName },
      { href: "/onboarding", label: "New venture", icon: "plus" as IconName },
      ...NAV,
      { href: "/events", label: "Logs", icon: "book" as IconName },
    ],
    [],
  );
  const filtered = actions.filter((action) =>
    action.label.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <div className="fixed inset-0 z-50 bg-ink/35 p-4" onClick={onClose}>
      <div
        className="mx-auto mt-20 max-w-lg rounded-md border border-rule bg-paper shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-rule px-3 py-2.5">
          <Icon name="search" size={14} className="text-ink-3" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Jump to..."
            className="h-8 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-3"
          />
          <button
            type="button"
            onClick={onClose}
            className="h-7 w-7 rounded-sm text-ink-3 hover:bg-sand hover:text-ink"
            aria-label="Close command palette"
          >
            <Icon name="close" size={13} className="mx-auto" />
          </button>
        </div>
        <div className="max-h-[360px] overflow-y-auto p-2">
          {filtered.map((action) => (
            <Link
              key={`${action.href}-${action.label}`}
              href={action.href}
              onClick={onClose}
              className={cn(
                "flex items-center gap-2 rounded-sm px-3 py-2 text-sm hover:bg-sand",
                isActive(pathname, action.href) ? "bg-sand text-ink" : "text-ink-2",
              )}
            >
              <Icon name={action.icon} size={15} />
              <span>{action.label}</span>
            </Link>
          ))}
          {filtered.length === 0 && (
            <div className="px-3 py-6 text-center text-sm text-ink-3">No matching command.</div>
          )}
        </div>
      </div>
    </div>
  );
}

// Crumbs derived from URL when no explicit override is provided. Keeps each
// page's call site simple — 90% of surfaces want "Helm / <Title>".
function deriveCrumbs(pathname: string): string[] {
  const segs = pathname.split("/").filter(Boolean);
  if (segs.length === 0) return ["Helm"];
  const top = segs[0] ?? "";
  const TITLE: Record<string, string> = {
    today: "Today",
    chat: "Chat",
    businesses: "Businesses",
    approvals: "Approvals",
    safety: "Safety",
    billing: "Billing",
    agents: "Agents",
    events: "Logs",
    money: "Money",
    onboarding: "New venture",
    connections: "Connections",
    studio: "Creative Studio",
  };
  const base = ["Helm", TITLE[top] ?? toTitle(top)];
  if (segs.length === 1) return base;
  if (segs[1] === "new") return [...base, "New"];
  return [...base, "Detail"];
}

function toTitle(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function isActive(pathname: string, href: string) {
  if (href === "/today") return pathname === "/today";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function initialsFrom(email?: string | null) {
  if (!email) return "—";
  const name = email.split("@")[0] ?? "";
  if (!name) return "—";
  const parts = name.split(/[._-]+/).filter(Boolean);
  if (parts.length >= 2) {
    const a = parts[0]?.[0] ?? "";
    const b = parts[1]?.[0] ?? "";
    return (a + b).toUpperCase();
  }
  return (name[0] + (name[1] ?? "")).toUpperCase();
}

function contextFromPath(pathname: string): string {
  if (pathname.startsWith("/today")) return "today";
  if (pathname.startsWith("/businesses")) return "businesses";
  if (pathname.startsWith("/approvals")) return "approvals";
  if (pathname.startsWith("/safety")) return "safety";
  if (pathname.startsWith("/billing")) return "billing";
  if (pathname.startsWith("/agents")) return "agents";
  if (pathname.startsWith("/events")) return "events";
  if (pathname.startsWith("/money")) return "money";
  if (pathname.startsWith("/onboarding")) return "onboarding";
  return "overview";
}
