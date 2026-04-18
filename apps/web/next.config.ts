import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  experimental: {
    // Keep the app opt-in about fetches — avoids hidden caching of our
    // SSE chat stream and API responses that should always be fresh.
    typedRoutes: true,
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

export default config;
