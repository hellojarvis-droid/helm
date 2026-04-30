"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
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

  return (
    <div className="min-h-screen grid grid-cols-[248px_1fr] bg-paper text-ink">
      <Sidebar pathname={pathname ?? ""} initials={initials} />
      <div className="flex flex-col min-h-screen overflow-hidden">
        <KillSwitchBanner />
        <Topbar crumbs={crumbs} initials={initials} />
        <main className="flex-1 overflow-y-auto scroll-paper paper-grain">
          {children}
        </main>
      </div>
      {!onChatRoute && <AtlasDock contextKey={contextKey} />}
    </div>
  );
}

function Sidebar({ pathname, initials }: { pathname: string; initials: string }) {
  const router = useRouter();

  async function signOut() {
    const supabase = supabaseBrowser();
    await supabase.auth.signOut();
    router.replace("/sign-in");
    router.refresh();
  }

  return (
    <aside className="bg-paper-2 border-r border-rule flex flex-col gap-5 px-4 py-5 overflow-hidden">
      <Link href="/today" className="flex items-center gap-2.5 px-1.5 py-1 hover:opacity-90">
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
              className={cn(
                "flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[14px] transition-colors",
                active
                  ? "bg-ink text-paper"
                  : "text-ink-2 hover:bg-sand hover:text-ink",
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

function Topbar({ crumbs, initials }: { crumbs: string[]; initials: string }) {
  return (
    <div className="flex items-center gap-4 px-7 py-3.5 border-b border-rule bg-paper">
      <BusinessSwitcher />
      <div className="text-[13px] text-ink-3">
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
        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-paper border border-rule rounded-sm text-[13px] text-ink-2 hover:bg-sand"
      >
        <Icon name="sparkle" size={13} /> New venture
      </Link>
      <button
        type="button"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-paper border border-rule rounded-sm text-[13px] text-ink-2 hover:bg-sand"
        aria-label="Search"
      >
        <Icon name="search" size={13} /> Search <kbd>⌘K</kbd>
      </button>
      <Link
        href="/approvals"
        aria-label="Notifications"
        className="inline-flex items-center px-2.5 py-1.5 bg-paper border border-rule rounded-sm text-ink-2 hover:bg-sand"
      >
        <Icon name="bell" size={13} />
      </Link>
      <BalanceChip />
      <div className="h-8 w-8 rounded-full bg-sand-2 grid place-items-center text-xs font-medium text-ink-2 border border-rule">
        {initials}
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
