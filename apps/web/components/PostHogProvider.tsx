"use client";

import { usePathname } from "next/navigation";
import posthog from "posthog-js";
import { PostHogProvider as Provider } from "posthog-js/react";
import { useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";

/**
 * PostHog client provider — wraps the app when NEXT_PUBLIC_POSTHOG_KEY is
 * configured. No-op otherwise (local dev without PostHog stays silent).
 *
 * Behaviour:
 *   - init on mount, client-side only
 *   - identify when the Supabase session resolves to a user
 *   - capture $pageview on every path change
 *   - privacy: session recording disabled by default (opt-in on the PH side)
 */
export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    if (!key) return;
    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com",
      capture_pageview: false, // we fire manually on route change below
      persistence: "localStorage+cookie",
      disable_session_recording: true,
      loaded: () => setReady(true),
    });
  }, []);

  // Identify once the Supabase session resolves.
  useEffect(() => {
    if (!ready) return;
    void supabaseBrowser()
      .auth.getUser()
      .then(({ data }) => {
        const u = data.user;
        if (u) {
          posthog.identify(u.id, { email: u.email ?? undefined });
        } else {
          posthog.reset();
        }
      });
  }, [ready]);

  // Fire $pageview on every path change.
  useEffect(() => {
    if (!ready) return;
    posthog.capture("$pageview", { path: pathname });
  }, [pathname, ready]);

  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key) return <>{children}</>;
  return <Provider client={posthog}>{children}</Provider>;
}
