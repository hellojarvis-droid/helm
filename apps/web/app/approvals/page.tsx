"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { type Approval, listApprovals, respondToApproval } from "@/lib/api";

type Tab = "pending" | "approved" | "denied" | "all";

const TABS: { key: Tab; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "denied", label: "Denied" },
  { key: "all", label: "All" },
];

export default function ApprovalsPage() {
  const [tab, setTab] = useState<Tab>("pending");
  const [rows, setRows] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    const filter = tab === "all" ? undefined : tab;
    listApprovals(filter)
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [tab]);

  async function respond(
    id: string,
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) {
    setError(null);
    try {
      const updated = await respondToApproval(id, status, modifications);
      setRows((prev) =>
        prev ? prev.map((r) => (r.id === id ? updated : r)).filter(matchesTab(tab)) : prev,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold tracking-tight">Approvals</h1>
        </div>

        <div className="flex gap-1 border-b border-iron/20 mb-4">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-4 py-2 text-sm border-b-2 transition-colors -mb-px",
                tab === t.key
                  ? "border-accent text-ink dark:text-paper"
                  : "border-transparent text-iron hover:text-ink dark:hover:text-paper",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <p className="text-sm text-danger mb-4">{error}</p>}

        {rows === null ? (
          <p className="text-sm text-iron">Loading…</p>
        ) : rows.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>Nothing here</CardTitle>
              <CardDescription>
                {tab === "pending"
                  ? "No approvals waiting on you. The agent is either idling or already executing approved work."
                  : `No ${tab} approvals yet.`}
              </CardDescription>
            </CardHeader>
          </Card>
        ) : (
          <div className="space-y-3">
            {rows.map((a) => (
              <ApprovalRow key={a.id} approval={a} onRespond={respond} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function ApprovalRow({
  approval,
  onRespond,
}: {
  approval: Approval;
  onRespond: (
    id: string,
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const expires = new Date(approval.expires_at).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
  const requested = new Date(approval.requested_at).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });

  const pending = approval.status === "pending";
  const isSpend =
    approval.kind === "spend" &&
    typeof approval.details?.amount_cents === "number" &&
    (approval.details.amount_cents as number) > 0;
  const borderClass = pending
    ? isSpend
      ? "border-accent border-2 bg-accent/5"
      : "border-accent/40 bg-accent/5"
    : "border-iron/20 bg-haze/40 dark:bg-ink/40";

  const amountCents = isSpend ? (approval.details.amount_cents as number) : 0;
  const merchant =
    typeof approval.details?.merchant_hint === "string"
      ? (approval.details.merchant_hint as string)
      : "";
  const purpose =
    typeof approval.details?.purpose === "string" ? (approval.details.purpose as string) : "";

  return (
    <div className={cn("rounded-lg border p-5", borderClass)}>
      <div className="flex items-start justify-between mb-2">
        <div className="text-xs uppercase tracking-wider font-semibold">
          {isSpend ? "Spend approval" : approval.kind} ·{" "}
          <span className="text-iron">{approval.status}</span>
        </div>
        <div className="text-xs text-iron text-right">
          <div>requested {requested}</div>
          {pending && <div>expires {expires}</div>}
        </div>
      </div>

      {isSpend ? (
        <>
          <div className="flex items-baseline gap-3 mb-3">
            <span className="text-4xl font-semibold tabular">
              ${(amountCents / 100).toFixed(2)}
            </span>
            {merchant ? <span className="text-sm text-iron">to {merchant}</span> : null}
          </div>
          {purpose ? (
            <div className="text-sm leading-relaxed mb-2">
              <span className="text-iron">Why: </span>
              {purpose}
            </div>
          ) : null}
          <p className="text-xs text-iron leading-relaxed mb-4">{approval.summary}</p>
        </>
      ) : (
        <p className="text-sm leading-relaxed mb-4">{approval.summary}</p>
      )}

      {pending && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="accent"
            size={isSpend ? "md" : "sm"}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await onRespond(approval.id, "approved");
              setBusy(false);
            }}
          >
            {isSpend ? `Approve $${(amountCents / 100).toFixed(0)}` : "Approve"}
          </Button>
          {isSpend && (
            <Button
              variant="outline"
              size="md"
              disabled={busy}
              title="Approves this spend AND raises the business's weekly cap to fit it."
              onClick={async () => {
                setBusy(true);
                await onRespond(approval.id, "modified", { raise_weekly_cap: true });
                setBusy(false);
              }}
            >
              Approve & raise cap
            </Button>
          )}
          <Button
            variant="outline"
            size={isSpend ? "md" : "sm"}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await onRespond(approval.id, "denied");
              setBusy(false);
            }}
          >
            Deny
          </Button>
        </div>
      )}
      <Link
        href={`/approvals/${approval.id}` as never}
        className="inline-block mt-3 text-xs text-iron hover:text-ink dark:hover:text-paper"
      >
        Open detail →
      </Link>
    </div>
  );
}

function matchesTab(tab: Tab): (a: Approval) => boolean {
  if (tab === "all") return () => true;
  return (a: Approval) => a.status === tab;
}
