import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";

interface CookieToSet {
  name: string;
  value: string;
  options?: CookieOptions;
}

/**
 * Server-side Supabase client. Reads the session cookie so Server Components
 * can fetch user state without round-tripping to the client. Writes go
 * through NextResponse cookies via setAll — `cookies()` from next/headers
 * is read-only inside server components, but available for mutation inside
 * route handlers / server actions / middleware.
 */
export async function supabaseServer() {
  const store = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return store.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          // Inside server components setAll is a no-op — the middleware
          // refreshes the session cookie on its way through.
          try {
            cookiesToSet.forEach(({ name, value, options }: CookieToSet) =>
              store.set(name, value, options),
            );
          } catch {
            // Ignore when called from a server component (no mutable cookies).
          }
        },
      },
    },
  );
}
