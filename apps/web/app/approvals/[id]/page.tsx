"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ApprovalWhy } from "@/components/chat/ApprovalWhy";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { type Approval, getApproval, respondToApproval } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

const STATUS_CHIP: Record<string, string> = {
  pending: "chip-terra",
  approved: "chip-sage",
  modified: "chip-terra",
  denied: "chip-rose",
  expired: "",
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
      <AppShell breadcrumbs={["Helm", "Approvals", "Detail"]}>
        <div className="px-10 py-8 max-w-3xl space-y-4">
          <p className="text-sm text-rose-2">{error}</p>
          <Link href="/approvals" className="text-sm text-ink-3 hover:text-ink">
            ← All approvals
          </Link>
        </div>
      </AppShell>
    );
  }

  if (!approval) {
    return (
      <AppShell breadcrumbs={["Helm", "Approvals", "Detail"]}>
        <div className="px-10 py-8">
          <p className="text-sm text-ink-3">Loading…</p>
        </div>
      </AppShell>
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
  const chipClass = STATUS_CHIP[approval.status] ?? "";

  return (
    <AppShell breadcrumbs={["Helm", "Approvals", approval.summary.slice(0, 24) + "…"]}>
      <div className="px-10 pt-8 pb-20 max-w-3xl space-y-6">
        <header>
          <span className={cn("chip mb-3", chipClass)}>
            {isSpend ? "Spend approval" : approval.kind} · {approval.status}
          </span>
          {isSpend ? (
            <div className="flex items-baseline gap-3 mt-2">
              <h1 className="font-serif text-[54px] leading-none tracking-tightest tabular">
                ${(amountCents / 100).toFixed(2)}
              </h1>
              {merchant ? <span className="text-sm text-ink-3">to {merchant}</span> : null}
            </div>
          ) : (
            <h1 className="font-serif text-[36px] leading-tight tracking-tightest mt-2">
              {approval.summary}
            </h1>
          )}
        </header>

        {isSpend && purpose ? (
          <Card>
            <CardHeader>
              <CardTitle>Why</CardTitle>
            </CardHeader>
            <p className="text-sm leading-relaxed text-ink">{purpose}</p>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <p className="text-sm leading-relaxed text-ink">{approval.summary}</p>
          <ApprovalWhy approvalId={approval.id} variant="prominent" />
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Timing</CardTitle>
          </CardHeader>
          <dl className="text-sm space-y-1">
            <div className="flex justify-between py-1 border-b border-rule last:border-b-0">
              <dt className="text-ink-3">Requested</dt>
              <dd className="font-mono text-xs">{requested}</dd>
            </div>
            <div className="flex justify-between py-1 border-b border-rule last:border-b-0">
              <dt className="text-ink-3">Expires</dt>
              <dd className="font-mono text-xs">{expires}</dd>
            </div>
            {responded ? (
              <div className="flex justify-between py-1 border-b border-rule last:border-b-0">
                <dt className="text-ink-3">Responded</dt>
                <dd className="font-mono text-xs">{responded}</dd>
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
          <pre className="text-xs bg-paper-2 p-4 rounded-sm overflow-x-auto font-mono border border-rule text-ink-2">
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

        {error ? <p className="text-sm text-rose-2">{error}</p> : null}

        <Link href="/approvals" className="inline-block text-sm text-ink-3 hover:text-ink">
          ← All approvals
        </Link>
      </div>
    </AppShell>
  );
}
