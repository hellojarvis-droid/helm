import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

interface CookieToSet {
  name: string;
  value: string;
  options?: CookieOptions;
}

/**
 * Middleware helper: refreshes the Supabase session cookie on every request.
 * Without this, the auth session would go stale mid-navigation and server
 * components would see a user they shouldn't.
 *
 * The returned `response` must be returned from `middleware.ts` so the
 * refreshed cookies make it to the browser.
 */
export async function updateSession(request: NextRequest): Promise<{
  user: { id: string; email: string | undefined } | null;
  response: NextResponse;
}> {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          cookiesToSet.forEach(({ name, value }: CookieToSet) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }: CookieToSet) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  return {
    user: user ? { id: user.id, email: user.email } : null,
    response,
  };
}
