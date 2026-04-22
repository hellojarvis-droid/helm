"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

/**
 * Root-layout error boundary. Catches errors thrown in the root layout
 * itself (when /app/error.tsx isn't reachable). Must include <html>
 * and <body> because the root layout failed to render. Plain inline
 * styles — global CSS isn't guaranteed to have loaded.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  const digest = error.digest;
  const mailto = digest
    ? `mailto:support@helm.app?subject=${encodeURIComponent(
        `Helm error — reference ${digest}`,
      )}&body=${encodeURIComponent(
        `I hit an error on Helm. Error reference: ${digest}\n\nWhat I was trying to do:\n`,
      )}`
    : "mailto:support@helm.app";

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily: "Inter, -apple-system, BlinkMacSystemFont, system-ui, sans-serif",
          display: "flex",
          minHeight: "100vh",
          alignItems: "center",
          justifyContent: "center",
          background: "#FAFAF8",
          color: "#0A0A0A",
        }}
      >
        <div style={{ maxWidth: 480, padding: 24, textAlign: "center" }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: 2,
              color: "#A8251A",
              textTransform: "uppercase",
              marginBottom: 12,
            }}
          >
            Helm hit a wall
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 600, margin: "0 0 12px" }}>
            We&apos;re sorry — the app crashed.
          </h1>
          <p style={{ fontSize: 14, color: "#6B6B6B", lineHeight: 1.5 }}>
            We&apos;ve logged the error. Reload to try again. If it keeps happening, email{" "}
            <a href={mailto} style={{ color: "#0A0A0A" }}>
              support@helm.app
            </a>{" "}
            with the reference below and we&apos;ll dig in.
          </p>
          {digest ? (
            <p
              style={{
                fontSize: 11,
                color: "#6B6B6B",
                fontFamily: "JetBrains Mono, ui-monospace, monospace",
                marginTop: 16,
              }}
            >
              Error reference: {digest}
            </p>
          ) : null}
          <button
            onClick={reset}
            style={{
              marginTop: 24,
              padding: "10px 18px",
              background: "#E85D1A",
              color: "#FAFAF8",
              border: 0,
              borderRadius: 6,
              fontSize: 14,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
