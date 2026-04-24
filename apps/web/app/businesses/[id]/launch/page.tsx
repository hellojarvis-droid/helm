"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  getBusiness,
  getLaunch,
  startLaunch,
  streamLaunch,
  type BusinessDetail,
  type LaunchSnapshot,
  type LaunchStep,
  type LaunchStreamEvent,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

const STEP_META: Record<string, { title: string; specialist: string; description: string }> = {
  stripe_connect: {
    title: "Opening the vault",
    specialist: "Harbor",
    description: "Creating a Stripe Connect account so your business can take money.",
  },
  issuing_card: {
    title: "Issuing the business card",
    specialist: "Harbor",
    description: "Virtual card with weekly caps and MCC allowlist programmed at Stripe.",
  },
  brand_kit: {
    title: "Designing the brand",
    specialist: "Creative Director",
    description: "Name, palette, typography, voice — a coherent identity Atlas can hand to every channel.",
  },
  storefront: {
    title: "Standing up the storefront",
    specialist: "Product Builder",
    description: "Shopify store, products loaded, theme set, policies installed.",
  },
  ad_accounts: {
    title: "Wiring the paid channels",
    specialist: "Ads Operator",
    description: "Verifying Meta, Google, and TikTok ad accounts so campaigns can launch.",
  },
  first_approval: {
    title: "First hand-off",
    specialist: "Atlas",
    description: "Preparing the first-week ad budget for your approval.",
  },
};

export default function LaunchPage({ params }: PageProps) {
  const { id } = use(params);
  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [snapshot, setSnapshot] = useState<LaunchSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Kick off: POST /launch (idempotent) then subscribe to SSE.
  const boot = useCallback(async () => {
    setError(null);
    try {
      const [bizData, existing] = await Promise.all([getBusiness(id), getLaunch(id)]);
      setBiz(bizData);
      if (!existing || existing.status === "cancelled" || existing.status === "failed") {
        const fresh = await startLaunch(id);
        setSnapshot(fresh);
      } else {
        setSnapshot(existing);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void boot();
  }, [boot]);

  // Subscribe to the SSE stream once we have an initial snapshot. Auto-reconnect
  // on transient drops by the browser — if streamLaunch throws, we log + exit.
  useEffect(() => {
    if (!snapshot) return;
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      setConnected(false);
      return;
    }
    const ac = new AbortController();
    abortRef.current = ac;
    setConnected(true);

    (async () => {
      try {
        for await (const ev of streamLaunch(id, ac.signal)) {
          applyEvent(ev, setSnapshot);
          if (ev.kind === "done" || ev.kind === "timeout") break;
        }
      } catch (e) {
        if (!ac.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        setConnected(false);
      }
    })();

    return () => ac.abort();
  }, [id, snapshot?.launch_id]);

  const terminal =
    snapshot?.status === "completed" ||
    snapshot?.status === "failed" ||
    snapshot?.status === "cancelled";

  return (
    <AppShell breadcrumbs={["Helm", "Businesses", biz?.name ?? "Launch", "Launch"]}>
      <div className="px-10 pt-8 pb-20 max-w-4xl">
        <header className="mb-8">
          <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">
            {snapshot?.status === "completed"
              ? "Launch complete"
              : snapshot?.status === "failed"
                ? "Launch failed"
                : snapshot?.status === "cancelled"
                  ? "Launch cancelled"
                  : "Launching"}
            {connected && " · live"}
          </div>
          <h1 className="font-serif text-[48px] leading-none tracking-tightest mb-3">
            {headerText(snapshot, biz)}
          </h1>
          <p className="text-sm text-ink-3 max-w-prose">
            {bodyText(snapshot, biz)}
          </p>
        </header>

        {error && (
          <div className="mb-5 rounded-md border border-rose-2/50 bg-rose-soft/50 p-4 text-sm text-rose-2">
            {error}
          </div>
        )}

        {snapshot ? (
          <ol className="space-y-3">
            {snapshot.steps.map((step, i) => (
              <StepCard
                key={step.id}
                step={step}
                prevCompleted={i === 0 ? true : snapshot.steps[i - 1]?.status === "completed"}
                isCurrent={snapshot.current_step === step.step_name}
              />
            ))}
          </ol>
        ) : (
          !error && <p className="text-sm text-ink-3">Preparing the bridge…</p>
        )}

        {terminal && snapshot && (
          <div className="mt-10 flex flex-wrap gap-3">
            {snapshot.status === "completed" || firstApprovalCreated(snapshot) ? (
              <Link
                href="/approvals"
                className="inline-flex items-center gap-1.5 px-4 h-11 text-sm rounded-sm bg-terracotta border border-terracotta text-paper hover:bg-terracotta-2 hover:border-terracotta-2"
              >
                <Icon name="check" size={13} /> Review first approval
              </Link>
            ) : null}
            <Link
              href={`/businesses/${id}`}
              className="inline-flex items-center gap-1.5 px-4 h-11 text-sm rounded-sm border border-rule bg-paper text-ink hover:bg-sand"
            >
              Open business
            </Link>
            <Link
              href="/today"
              className="inline-flex items-center gap-1.5 px-4 h-11 text-sm rounded-sm border border-rule bg-paper text-ink hover:bg-sand"
            >
              Back to Today
            </Link>
            {snapshot.status === "failed" && (
              <Button
                variant="outline"
                size="lg"
                onClick={() => {
                  abortRef.current?.abort();
                  void boot();
                }}
              >
                Retry launch
              </Button>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function StepCard({
  step,
  prevCompleted,
  isCurrent,
}: {
  step: LaunchStep;
  prevCompleted: boolean;
  isCurrent: boolean;
}) {
  const meta = STEP_META[step.step_name] ?? {
    title: step.step_name,
    specialist: "—",
    description: "",
  };
  const isRunning = step.status === "running" || (isCurrent && step.status === "pending");
  const isDone = step.status === "completed";
  const isSkipped = step.status === "skipped";
  const isFailed = step.status === "failed";

  return (
    <li
      className={cn(
        "rounded-md border p-5 transition-colors",
        isRunning
          ? "border-terracotta/60 bg-terracotta-soft/30"
          : isDone
            ? "border-sage/40 bg-sage-soft/30"
            : isFailed
              ? "border-rose-2/40 bg-rose-soft/40"
              : isSkipped
                ? "border-rule bg-paper-2"
                : "border-rule bg-paper opacity-70",
      )}
    >
      <div className="flex items-start gap-4">
        <StatusDot status={step.status} running={isRunning} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <h3 className="font-serif text-[22px] leading-tight tracking-[-0.01em]">
              {meta.title}
            </h3>
            <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">
              {meta.specialist}
            </span>
            <span className="ml-auto text-[11px] uppercase tracking-[0.06em] text-ink-3">
              {statusLabel(step.status, prevCompleted)}
            </span>
          </div>
          <p className="text-sm text-ink-2 mt-1">{meta.description}</p>
          {isSkipped && typeof step.output?.reason === "string" && (
            <p className="mt-2 text-xs text-ink-3">
              Skipped — {humanizeReason(step.output.reason)}
            </p>
          )}
          {isFailed && step.error && (
            <p className="mt-2 text-xs text-rose-2 font-mono">{step.error}</p>
          )}
          {isDone && stepOutputSummary(step) && (
            <p className="mt-2 text-xs text-ink-3 font-mono">{stepOutputSummary(step)}</p>
          )}
        </div>
      </div>
    </li>
  );
}

function StatusDot({
  status,
  running,
}: {
  status: LaunchStep["status"];
  running: boolean;
}) {
  if (running) {
    return (
      <div className="shrink-0 h-7 w-7 grid place-items-center">
        <span className="h-3 w-3 rounded-full bg-terracotta animate-pulse shadow-[0_0_0_5px_var(--terracotta-soft)]" />
      </div>
    );
  }
  if (status === "completed") {
    return (
      <div className="shrink-0 h-7 w-7 grid place-items-center rounded-full bg-sage-soft text-sage-2">
        <Icon name="check" size={14} />
      </div>
    );
  }
  if (status === "skipped") {
    return (
      <div className="shrink-0 h-7 w-7 grid place-items-center rounded-full bg-sand text-ink-3">
        <Icon name="more" size={14} />
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className="shrink-0 h-7 w-7 grid place-items-center rounded-full bg-rose-soft text-rose-2">
        <Icon name="close" size={14} />
      </div>
    );
  }
  return <div className="shrink-0 h-7 w-7 grid place-items-center">
    <span className="h-2 w-2 rounded-full bg-sand-2" />
  </div>;
}

function statusLabel(status: LaunchStep["status"], prevCompleted: boolean): string {
  if (status === "completed") return "Done";
  if (status === "running") return "Running";
  if (status === "failed") return "Failed";
  if (status === "skipped") return "Skipped";
  return prevCompleted ? "Up next" : "Waiting";
}

function stepOutputSummary(step: LaunchStep): string {
  const out = step.output || {};
  switch (step.step_name) {
    case "stripe_connect": {
      const acct = String(out.stripe_account_id ?? "");
      return acct ? `acct ${acct}` : "";
    }
    case "issuing_card": {
      const card = String(out.card_id ?? "");
      const cap = Number(out.weekly_cap_cents ?? 0);
      return card ? `${card} · $${Math.round(cap / 100)}/wk cap` : "";
    }
    case "brand_kit": {
      const fields = (out.fields_populated as string[] | undefined) ?? [];
      return fields.length ? `populated: ${fields.join(", ")}` : "";
    }
    case "ad_accounts": {
      const channels = (out.channels_checked as string[] | undefined) ?? [];
      return channels.length ? `channels: ${channels.join(", ")}` : "";
    }
    case "first_approval": {
      const amt = Number(out.amount_cents ?? 0);
      return amt ? `$${Math.round(amt / 100)} approval queued` : "";
    }
    default:
      return "";
  }
}

function humanizeReason(raw: string): string {
  const MAP: Record<string, string> = {
    stripe_not_configured: "Stripe isn't configured on this deployment yet.",
    issuing_feature_flag_off: "Stripe Issuing hasn't been approved for this workspace.",
    no_stripe_account_yet: "Stripe Connect account not ready — skipping issuing.",
    shopify_not_connected: "Shopify isn't connected — connect it in Integrations to launch a storefront.",
    no_ad_platforms_connected: "No Meta/Google/TikTok account connected yet.",
  };
  return MAP[raw] ?? raw;
}

function headerText(snapshot: LaunchSnapshot | null, biz: BusinessDetail | null): string {
  if (!snapshot) return "Bringing the bridge online…";
  if (snapshot.status === "completed") {
    return biz ? `${biz.name} is live.` : "Your business is live.";
  }
  if (snapshot.status === "failed") return "Something stalled.";
  if (snapshot.status === "cancelled") return "Launch paused.";
  return biz ? `Launching ${biz.name}…` : "Launching…";
}

function bodyText(snapshot: LaunchSnapshot | null, biz: BusinessDetail | null): string {
  if (!snapshot) return "Atlas is assembling the specialists.";
  if (snapshot.status === "completed") {
    return "Every step the swarm could run is done. Approve the first ad budget below to let Atlas hand off.";
  }
  if (snapshot.status === "failed") {
    return `${snapshot.error ?? "One or more steps failed"}. Retry below once you've resolved the cause — completed steps won't re-run.`;
  }
  if (snapshot.status === "cancelled") {
    return "The kill switch is on. Turn it off in Safety to resume.";
  }
  return "The specialists are working. This page updates live.";
}

function firstApprovalCreated(snapshot: LaunchSnapshot): boolean {
  return snapshot.steps.some((s) => s.step_name === "first_approval" && s.status === "completed");
}

function applyEvent(
  ev: LaunchStreamEvent,
  setSnapshot: React.Dispatch<React.SetStateAction<LaunchSnapshot | null>>,
) {
  if (ev.kind === "snapshot") {
    setSnapshot(ev.snapshot);
    return;
  }
  if (ev.kind !== "step") return;
  // Translate agent_events rows into incremental step state updates so the
  // UI reacts instantly without waiting for the next snapshot.
  setSnapshot((prev) => {
    if (!prev) return prev;
    const payload = ev.payload ?? {};
    const stepName = typeof payload.step === "string" ? payload.step : null;
    if (!stepName) return prev;
    const mutator = {
      launch_step_started: (s: LaunchStep) => ({ ...s, status: "running" as const }),
      launch_step_completed: (s: LaunchStep) => ({
        ...s,
        status: "completed" as const,
        output: (payload.output as Record<string, unknown>) ?? s.output,
      }),
      launch_step_failed: (s: LaunchStep) => ({
        ...s,
        status: "failed" as const,
        error: (payload.error as string) ?? s.error,
      }),
      launch_step_skipped: (s: LaunchStep) => ({
        ...s,
        status: "skipped" as const,
        output: (payload.output as Record<string, unknown>) ?? s.output,
      }),
    }[ev.event_type];
    if (!mutator) return prev;
    return {
      ...prev,
      current_step: ev.event_type === "launch_step_started" ? stepName : prev.current_step,
      steps: prev.steps.map((s) => (s.step_name === stepName ? mutator(s) : s)),
    };
  });
}
