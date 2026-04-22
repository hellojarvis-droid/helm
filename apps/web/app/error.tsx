"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";
import { Button } from "@/components/ui/Button";

/**
 * Next.js 15 route-segment error boundary. Catches unhandled React
 * errors thrown by any descendant of the (segments under) /app and
 * renders a human fallback instead of the default whitescreen. Reports
 * to Sentry on mount when configured.
 */
export default function Error({
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
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center space-y-4">
        <div className="text-xs font-semibold tracking-widest text-danger uppercase">
          Something went wrong
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">The page hit an error.</h1>
        <p className="text-sm text-iron leading-relaxed">
          We&apos;ve logged it. Try again — or, if it keeps happening, email support and we&apos;ll
          dig in.
        </p>
        {digest ? (
          <p className="text-xs text-iron font-mono">
            Error reference: <span className="select-all">{digest}</span>
          </p>
        ) : null}
        <div className="flex items-center justify-center gap-2 pt-2">
          <Button variant="accent" onClick={reset}>
            Try again
          </Button>
          <a
            href={mailto}
            className="inline-flex items-center justify-center h-10 px-4 text-sm rounded-md border border-iron/30 hover:bg-haze"
          >
            Email support
          </a>
        </div>
      </div>
    </div>
  );
}
