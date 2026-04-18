import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

/**
 * - Refreshes the Supabase session on every request (cookie rotation).
 * - Redirects unauthenticated users away from protected routes.
 * - Redirects signed-in users away from auth routes.
 */
const PROTECTED = ["/today", "/chat", "/businesses", "/approvals", "/safety"];
const AUTH_ROUTES = ["/sign-in", "/sign-up"];

export async function middleware(request: NextRequest) {
  const { user, response } = await updateSession(request);
  const { pathname } = request.nextUrl;

  const needsAuth = PROTECTED.some((p) => pathname.startsWith(p));
  if (needsAuth && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  const isAuthRoute = AUTH_ROUTES.some((p) => pathname.startsWith(p));
  if (isAuthRoute && user) {
    const url = request.nextUrl.clone();
    url.pathname = "/today";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: [
    // Match everything except static files and Next internals.
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|webp|woff2)$).*)",
  ],
};
