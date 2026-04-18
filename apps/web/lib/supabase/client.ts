"use client";

import { createBrowserClient } from "@supabase/ssr";
import { clientEnv } from "@/lib/env";

/**
 * Browser-side Supabase client. Use this inside Client Components / event
 * handlers. For server components, use `lib/supabase/server.ts` — it reads
 * cookies directly instead of relying on the browser's session.
 */
export function supabaseBrowser() {
  const env = clientEnv();
  return createBrowserClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
}
