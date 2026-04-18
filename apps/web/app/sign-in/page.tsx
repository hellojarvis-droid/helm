"use client";

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
  const next = params.get("next") ?? "/chat";

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
      const fn = mode === "signin" ? supabase.auth.signInWithPassword : supabase.auth.signUp;
      const { error } = await fn({ email, password });
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
    <main className="min-h-screen grid place-items-center p-6">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-iron/20 p-8 bg-haze/30 dark:bg-ink/40"
      >
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Helm</h1>
          <p className="text-sm text-iron mt-1">
            {mode === "signin" ? "Sign in to your account." : "Create an account."}
          </p>
        </div>

        <div className="space-y-2">
          <label className="text-sm">Email</label>
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm">Password</label>
          <Input
            type="password"
            required
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {err && <p className="text-sm text-danger">{err}</p>}

        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? "…" : mode === "signin" ? "Sign in" : "Create account"}
        </Button>

        <button
          type="button"
          className="text-sm text-iron w-full hover:text-ink dark:hover:text-paper"
          onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
        >
          {mode === "signin" ? "Need an account? Sign up" : "Already have one? Sign in"}
        </button>
      </form>
    </main>
  );
}
