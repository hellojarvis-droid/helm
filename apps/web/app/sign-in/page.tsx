"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { supabaseBrowser } from "@/lib/supabase/client";

// useSearchParams needs a Suspense boundary under Next 15's static-first
// build. Wrap the inner form component; the page itself stays server-safe.
export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignInForm />
    </Suspense>
  );
}

function SignInForm() {
  const router = useRouter();
  const params = useSearchParams();
  // `upgrade=operator|portfolio` from /pricing — route to /billing post-sign-in
  // so the Checkout buttons are one tap away. Falls back to ?next=… or /today.
  const upgrade = params.get("upgrade");
  const next = params.get("next") ?? (upgrade ? "/billing" : "/today");

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const supabase = supabaseBrowser();
      const { error } =
        mode === "signin"
          ? await supabase.auth.signInWithPassword({ email, password })
          : await supabase.auth.signUp({ email, password });
      if (error) {
        setErr(error.message);
        return;
      }
      router.replace(next);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-paper paper-grain grid place-items-center p-6">
      <div className="w-full max-w-sm">
        <Link
          href="/"
          className="inline-flex items-center gap-2 mb-10 text-ink-3 hover:text-ink text-sm"
        >
          <div className="h-7 w-7 grid place-items-center rounded-md bg-ink text-paper font-serif text-[18px] leading-none">
            H
          </div>
          <span className="font-semibold text-ink">Helm</span>
        </Link>

        <form onSubmit={submit} className="space-y-4 rounded-md border border-rule bg-paper p-8">
          <div className="mb-2">
            <h1 className="font-serif text-[32px] leading-tight tracking-tightest mb-1">
              {mode === "signin" ? "Welcome back." : "Start your holdings."}
            </h1>
            <p className="text-sm text-ink-3">
              {mode === "signin"
                ? "Sign in to your cockpit."
                : "Atlas will be waiting on the bridge."}
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Email
            </label>
            <Input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@holdings.co"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
              Password
            </label>
            <Input
              type="password"
              required
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>

          {err && <p className="text-sm text-rose-2">{err}</p>}

          <Button type="submit" variant="accent" size="lg" className="w-full" disabled={busy}>
            {busy ? "…" : mode === "signin" ? "Sign in" : "Create account"}
          </Button>

          <button
            type="button"
            className="text-sm text-ink-3 hover:text-ink w-full text-center"
            onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
          >
            {mode === "signin" ? "Need an account? Sign up" : "Already have one? Sign in"}
          </button>
        </form>

        <div className="mt-6 text-center text-xs text-ink-3">
          <Link href="/terms" className="hover:text-ink">
            Terms
          </Link>
          <span className="mx-2">·</span>
          <Link href="/privacy" className="hover:text-ink">
            Privacy
          </Link>
        </div>
      </div>
    </main>
  );
}
