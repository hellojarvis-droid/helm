"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ApprovalWhy } from "@/components/chat/ApprovalWhy";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
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
    <AppShell breadcrumbs={["Helm", "Approvals"]}>
      <div className="px-10 pt-8 pb-20 max-w-4xl">
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className="font-serif text-[44px] leading-none tracking-tightest mb-2">
              Approvals
            </h1>
            <p className="text-sm text-ink-3">
              Every action the swarm wants your sign-off on. Big spend, publishing, data deletes.
            </p>
          </div>
        </div>

        <div className="inline-flex gap-0.5 p-[3px] bg-sand rounded-[8px] mb-6">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-3.5 py-1.5 text-[12.5px] rounded-[6px]",
                tab === t.key ? "bg-paper text-ink shadow-sm" : "text-ink-3 hover:text-ink",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <p className="text-sm text-rose-2 mb-4">{error}</p>}

        {rows === null ? (
          <p className="text-sm text-ink-3">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="rounded-md border border-rule bg-paper p-8 max-w-xl">
            <div className="font-serif text-[22px] leading-tight mb-2">Nothing here.</div>
            <p className="text-sm text-ink-3">
              {tab === "pending"
                ? "No approvals waiting on you. The agent is either idling or already executing approved work."
                : `No ${tab} approvals yet.`}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {rows.map((a) => (
              <ApprovalRow key={a.id} approval={a} onRespond={respond} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
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

  const amountCents = isSpend ? (approval.details.amount_cents as number) : 0;
  const merchant =
    typeof approval.details?.merchant_hint === "string"
      ? (approval.details.merchant_hint as string)
      : "";
  const purpose =
    typeof approval.details?.purpose === "string" ? (approval.details.purpose as string) : "";

  const borderClass = pending
    ? isSpend
      ? "border-terracotta border-2 bg-terracotta-soft/30"
      : "border-terracotta/50 bg-terracotta-soft/20"
    : "border-rule bg-paper";

  return (
    <div className={cn("rounded-md border p-6", borderClass)}>
      <div className="flex items-start justify-between mb-3">
        <span className={cn("chip", pending ? "chip-terra" : "")}>
          {isSpend ? "Spend approval" : approval.kind} · {approval.status}
        </span>
        <div className="text-xs text-ink-3 text-right font-mono">
          <div>requested {requested}</div>
          {pending && <div>expires {expires}</div>}
        </div>
      </div>

      {isSpend ? (
        <>
          <div className="flex items-baseline gap-3 mb-3">
            <span className="font-serif text-[44px] leading-none tracking-tightest tabular">
              ${(amountCents / 100).toFixed(2)}
            </span>
            {merchant ? <span className="text-sm text-ink-3">to {merchant}</span> : null}
          </div>
          {purpose ? (
            <div className="text-sm leading-relaxed mb-3 text-ink-2">
              <span className="text-ink-3">Why: </span>
              {purpose}
            </div>
          ) : null}
          <p className="text-xs text-ink-3 leading-relaxed mb-4">{approval.summary}</p>
        </>
      ) : (
        <p className="text-sm leading-relaxed mb-4 text-ink">{approval.summary}</p>
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
      <div className="flex items-center gap-4 mt-3">
        <Link
          href={`/approvals/${approval.id}`}
          className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-ink"
        >
          Open detail <Icon name="arrowUp" size={10} className="rotate-90" />
        </Link>
      </div>
      <ApprovalWhy approvalId={approval.id} />
    </div>
  );
}

function matchesTab(tab: Tab): (a: Approval) => boolean {
  if (tab === "all") return () => true;
  return (a: Approval) => a.status === tab;
}
