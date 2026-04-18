"use client";

import { Button } from "@/components/ui/Button";

interface ApprovalCardProps {
  approval_id: string;
  approval_kind: string;
  summary: string;
  expires_at: string;
  onRespond?: (status: "approved" | "denied") => void;
}

export function ApprovalCard({
  approval_id,
  approval_kind,
  summary,
  expires_at,
  onRespond,
}: ApprovalCardProps) {
  const expires = new Date(expires_at).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
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
