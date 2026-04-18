"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { KillSwitchBanner } from "@/components/KillSwitchBanner";
import { cn } from "@/lib/cn";
import { supabaseBrowser } from "@/lib/supabase/client";

const items = [
  { href: "/today" as const, label: "Today" },
  { href: "/chat" as const, label: "Chat" },
  { href: "/businesses" as const, label: "Businesses" },
  { href: "/approvals" as const, label: "Approvals" },
  { href: "/safety" as const, label: "Safety" },
];

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  async function signOut() {
    const supabase = supabaseBrowser();
    await supabase.auth.signOut();
    router.replace("/sign-in");
    router.refresh();
  }

  return (
    <>
      <KillSwitchBanner />
      <nav className="flex items-center justify-between px-6 py-3 border-b border-iron/20">
        <div className="flex items-center gap-6">
          <Link href="/chat" className="text-lg font-semibold tracking-tight">
            Helm
          </Link>
          <div className="flex items-center gap-3">
            {items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "text-sm transition-colors",
                  pathname.startsWith(item.href)
                    ? "text-ink dark:text-paper"
                    : "text-iron hover:text-ink dark:hover:text-paper",
                )}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </div>
        <button
          onClick={signOut}
          className="text-sm text-iron hover:text-ink dark:hover:text-paper"
        >
          Sign out
        </button>
      </nav>
    </>
  );
}
