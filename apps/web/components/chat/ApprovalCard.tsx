"use client";

import { Button } from "@/components/ui/Button";

interface ApprovalCardProps {
  approval_id: string;
  approval_kind: string;
  summary: string;
  expires_at: string;
  details?: Record<string, unknown>;
  onRespond?: (
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) => void;
}

export function ApprovalCard(props: ApprovalCardProps) {
  if (props.approval_kind === "spend" && hasSpendDetails(props.details)) {
    return <SpendApprovalCard {...props} />;
  }
  return <GenericApprovalCard {...props} />;
}

function GenericApprovalCard({
  approval_id,
  approval_kind,
  summary,
  expires_at,
  onRespond,
}: ApprovalCardProps) {
  const expires = formatExpires(expires_at);
  return (
    <div className="rounded-lg border border-accent/40 bg-accent/5 p-5 my-3 max-w-2xl">
      <div className="flex items-start justify-between mb-2">
        <div className="text-xs uppercase tracking-wider text-accent font-semibold">
          Approval · {approval_kind}
        </div>
        <div className="text-xs text-iron">expires {expires}</div>
      </div>
      <p className="text-sm leading-relaxed mb-4">{summary}</p>
      <div className="flex gap-2">
        <Button
          variant="accent"
          size="sm"
          onClick={() => onRespond?.("approved")}
          aria-label={`Approve ${approval_id}`}
        >
          Approve
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onRespond?.("denied")}
          aria-label={`Deny ${approval_id}`}
        >
          Deny
        </Button>
      </div>
    </div>
  );
}

function SpendApprovalCard({
  approval_id,
  summary,
  expires_at,
  details,
  onRespond,
}: ApprovalCardProps) {
  const d = details ?? {};
  const amountCents = typeof d.amount_cents === "number" ? d.amount_cents : 0;
  const merchant = typeof d.merchant_hint === "string" ? d.merchant_hint : "";
  const purpose = typeof d.purpose === "string" ? d.purpose : "";
  const expires = formatExpires(expires_at);

  return (
    <div className="rounded-lg border-2 border-accent bg-accent/5 p-5 my-3 max-w-2xl">
      <div className="flex items-baseline justify-between mb-3">
        <div className="text-xs uppercase tracking-wider text-accent font-semibold">
          Spend approval
        </div>
        <div className="text-xs text-iron">expires {expires}</div>
      </div>

      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-4xl font-semibold tabular text-ink dark:text-paper">
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

      <p className="text-xs text-iron leading-relaxed mb-4">{summary}</p>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="accent"
          onClick={() => onRespond?.("approved")}
          aria-label={`Approve ${approval_id}`}
        >
          Approve ${(amountCents / 100).toFixed(0)}
        </Button>
        <Button
          variant="outline"
          onClick={() => onRespond?.("modified", { raise_weekly_cap: true })}
          aria-label={`Approve and raise weekly cap for ${approval_id}`}
          title="Approves this spend AND raises the business's weekly cap to fit it."
        >
          Approve & raise cap
        </Button>
        <Button
          variant="outline"
          onClick={() => onRespond?.("denied")}
          aria-label={`Deny ${approval_id}`}
        >
          Deny
        </Button>
      </div>
    </div>
  );
}

function hasSpendDetails(d: Record<string, unknown> | undefined): boolean {
  return !!d && typeof d.amount_cents === "number" && d.amount_cents > 0;
}

function formatExpires(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
}
