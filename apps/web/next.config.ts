import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";

// CSP / security headers. Phase 8.7 launch-readiness item.
//
// CSP is intentionally not "no-eval / no-inline" strict — Next.js server
// components inject some inline runtime payloads, and Sentry's tracing
// init runs from a synthetic script. We allow 'unsafe-inline' on scripts
// for now and tighten later via nonce-based CSP when we move off SSR
// hydration patches.
function buildCSP(): string {
  const apiBase = process.env.NEXT_PUBLIC_HELM_API_BASE ?? "http://localhost:8000";
  const supabase = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const sentryHost = "https://*.sentry.io https://*.ingest.sentry.io";
  const posthogHost =
    process.env.NEXT_PUBLIC_POSTHOG_HOST ??
    "https://us.i.posthog.com https://us-assets.i.posthog.com";
  const stripe = "https://*.stripe.com https://js.stripe.com";

  const connect = [
    "'self'",
    apiBase,
    supabase,
    `${supabase.replace("https://", "wss://")}`, // Supabase Realtime
    sentryHost,
    posthogHost,
    stripe,
  ]
    .filter(Boolean)
    .join(" ");

  return [
    "default-src 'self'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    `script-src 'self' 'unsafe-inline' 'unsafe-eval' ${stripe} ${posthogHost}`,
    `connect-src ${connect}`,
    `frame-src ${stripe}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
}

const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(self), geolocation=(), interest-cohort=()",
  },
  // HSTS only in prod — http localhost during dev would lock the browser.
  ...(process.env.NODE_ENV === "production"
    ? [
        {
          key: "Strict-Transport-Security",
          value: "max-age=63072000; includeSubDomains; preload",
        },
      ]
    : []),
  { key: "Content-Security-Policy", value: buildCSP() },
];

const config: NextConfig = {
  reactStrictMode: true,
  experimental: {
    // Keep the app opt-in about fetches — avoids hidden caching of our
    // SSE chat stream and API responses that should always be fresh.
    typedRoutes: true,
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async rewrites() {
    // Optional: proxy /api/* to the backend in local dev so the browser can
    // treat backend and frontend as same-origin (no CORS in dev). In prod
    // we talk to HELM_API_BASE directly from client code.
    if (process.env.NODE_ENV !== "development") return [];
    const apiBase = process.env.NEXT_PUBLIC_HELM_API_BASE ?? "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
  },
};

// Wrap with Sentry only when the project is configured. Source-maps upload
// is skipped when SENTRY_AUTH_TOKEN is missing so local dev and CI without
// Sentry secrets still build cleanly.
export default process.env.NEXT_PUBLIC_SENTRY_DSN
  ? withSentryConfig(config, {
      silent: true,
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      disableLogger: true,
      widenClientFileUpload: true,
      sourcemaps: {
        disable: false,
      },
    })
  : config;
