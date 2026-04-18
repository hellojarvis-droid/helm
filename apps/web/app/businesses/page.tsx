"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { listBusinesses, type Business } from "@/lib/api";

export default function BusinessesPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Business[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listBusinesses()
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold tracking-tight">Businesses</h1>
          <Button onClick={() => router.push("/businesses/new")}>New</Button>
        </div>

        {error && <div className="text-sm text-danger mb-4">{error}</div>}

        {rows === null ? (
          <div className="text-sm text-iron">Loading…</div>
        ) : rows.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>No businesses yet</CardTitle>
              <CardDescription>
                Start one — the CEO Agent will help you pick an idea, brand it, and launch the
                storefront.
              </CardDescription>
            </CardHeader>
            <Button onClick={() => router.push("/businesses/new")}>Create your first</Button>
          </Card>
        ) : (
          <div className="grid gap-3">
            {rows.map((b) => (
              <Link key={b.id} href={{ pathname: "/chat" }}>
                <Card className="hover:border-accent/40 transition-colors cursor-pointer">
                  <div className="flex items-baseline justify-between">
                    <div>
                      <div className="font-medium">{b.name}</div>
                      <div className="text-xs text-iron">{b.vertical}</div>
                    </div>
                    <div className="text-xs text-iron tabular">
                      ${(b.weekly_spend_cap_cents / 100).toFixed(0)}/wk · {b.status}
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
