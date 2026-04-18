/**
 * Next.js 15 instrumentation hook. Loaded exactly once at server startup
 * (Node runtime AND edge runtime). Per the Sentry Next.js integration, we
 * import the matching config module so Sentry.init runs in the right
 * runtime context.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}
