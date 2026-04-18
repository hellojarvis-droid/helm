"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { type Approval, getApproval, respondToApproval } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

const STATUS_TINT: Record<string, string> = {
  pending: "text-warning",
  approved: "text-success",
  modified: "text-accent",
  denied: "text-danger",
  expired: "text-iron",
};

export default function ApprovalDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getApproval(id)
      .then(setApproval)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  async function respond(
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) {
    setBusy(true);
    setError(null);
    try {
      const updated = await respondToApproval(id, status, modifications);
      setApproval(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !approval) {
    return (
      <div className="min-h-screen">
        <Nav />
        <main className="max-w-3xl mx-auto px-6 py-8 space-y-4">
          <p className="text-sm text-danger">{error}</p>
          <Link href={{ pathname: "/approvals" }} className="text-sm text-iron">
            ← All approvals
          </Link>
        </main>
      </div>
    );
  }

  if (!approval) {
    return (
      <div className="min-h-screen">
        <Nav />
        <main className="max-w-3xl mx-auto px-6 py-8">
          <p className="text-sm text-iron">Loading…</p>
        </main>
      </div>
    );
  }

  const isSpend =
    approval.kind === "spend" &&
    typeof approval.details?.amount_cents === "number" &&
    (approval.details.amount_cents as number) > 0;
  const amountCents = isSpend ? (approval.details.amount_cents as number) : 0;
  const merchant =
    typeof approval.details?.merchant_hint === "string"
      ? (approval.details.merchant_hint as string)
      : "";
  const purpose =
    typeof approval.details?.purpose === "string" ? (approval.details.purpose as string) : "";
  const requested = new Date(approval.requested_at).toLocaleString();
  const responded = approval.responded_at ? new Date(approval.responded_at).toLocaleString() : null;
  const expires = new Date(approval.expires_at).toLocaleString();
  const tint = STATUS_TINT[approval.status] ?? "text-iron";

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header>
          <div className={`text-xs font-semibold tracking-widest uppercase mb-1 ${tint}`}>
            {isSpend ? "Spend approval" : approval.kind} · {approval.status}
          </div>
          {isSpend ? (
            <div className="flex items-baseline gap-3">
              <h1 className="text-4xl font-semibold tabular">${(amountCents / 100).toFixed(2)}</h1>
              {merchant ? <span className="text-sm text-iron">to {merchant}</span> : null}
            </div>
          ) : (
            <h1 className="text-2xl font-semibold tracking-tight">{approval.summary}</h1>
          )}
        </header>

        {isSpend && purpose ? (
          <Card>
            <CardHeader>
              <CardTitle>Why</CardTitle>
            </CardHeader>
            <p className="text-sm leading-relaxed">{purpose}</p>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <p className="text-sm leading-relaxed">{approval.summary}</p>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Timing</CardTitle>
          </CardHeader>
          <dl className="text-sm space-y-1">
            <div className="flex justify-between">
              <dt className="text-iron">Requested</dt>
              <dd className="tabular">{requested}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-iron">Expires</dt>
              <dd className="tabular">{expires}</dd>
            </div>
            {responded ? (
              <div className="flex justify-between">
                <dt className="text-iron">Responded</dt>
                <dd className="tabular">{responded}</dd>
              </div>
            ) : null}
          </dl>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
            <CardDescription>
              Raw payload the agent sent with the approval. Anything specialists need to act on
              after you respond lives here.
            </CardDescription>
          </CardHeader>
          <pre className="text-xs bg-haze/40 dark:bg-ink/40 p-4 rounded-md overflow-x-auto font-mono">
            {JSON.stringify(approval.details, null, 2)}
          </pre>
        </Card>

        {approval.status === "pending" ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="accent" disabled={busy} onClick={() => respond("approved")}>
              {isSpend ? `Approve $${(amountCents / 100).toFixed(0)}` : "Approve"}
            </Button>
            {isSpend ? (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => respond("modified", { raise_weekly_cap: true })}
              >
                Approve & raise cap
              </Button>
            ) : null}
            <Button variant="outline" disabled={busy} onClick={() => respond("denied")}>
              Deny
            </Button>
          </div>
        ) : null}

        {error ? <p className="text-sm text-danger">{error}</p> : null}

        <Link
          href={{ pathname: "/approvals" }}
          className="inline-block text-sm text-iron hover:text-ink dark:hover:text-paper"
        >
          ← All approvals
        </Link>
      </main>
    </div>
  );
}
