"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { PreviewFrame } from "@/components/builder/PreviewFrame";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  apiFetch,
  approveBuilderPlan,
  getBuilderProject,
  listBuilderFiles,
  listBuilderPlans,
  proposeBuilderPlan,
  rejectBuilderPlan,
  undoBuilderProject,
  verifyBuilderProject,
  type BuilderFile,
  type BuilderPlan,
  type BuilderProject,
  type BuilderVerifyReport,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function BuilderWorkspace({ params }: PageProps) {
  const { id } = use(params);
  const [project, setProject] = useState<BuilderProject | null>(null);
  const [plans, setPlans] = useState<BuilderPlan[]>([]);
  const [files, setFiles] = useState<BuilderFile[]>([]);
  const [verify, setVerify] = useState<BuilderVerifyReport | null>(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, pl, fs, vr] = await Promise.all([
        getBuilderProject(id),
        listBuilderPlans(id),
        listBuilderFiles(id),
        verifyBuilderProject(id).catch(() => null),
      ]);
      setProject(p);
      setPlans(pl);
      setFiles(fs);
      setVerify(vr);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [plans.length]);

  const onAsk = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await proposeBuilderPlan(id, prompt.trim());
      setPrompt("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onApprove = async (planId: string) => {
    setBusy(true);
    setError(null);
    try {
      await approveBuilderPlan(planId);
      await refresh();
      // Force the preview to re-mount with the new file tree.
      setPreviewKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onReject = async (planId: string) => {
    try {
      await rejectBuilderPlan(planId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onUndo = async () => {
    if (!confirm("Restore the last working version?")) return;
    try {
      await undoBuilderProject(id);
      await refresh();
      setPreviewKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onExportZip = async () => {
    try {
      const res = await apiFetch(`/builder/projects/${id}/export/zip`);
      if (!res.ok) throw new Error(`export failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${project?.slug ?? "project"}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (!project) {
    return (
      <div className="mx-auto max-w-[800px] px-8 py-10">
        <div className="text-[13px] text-ink-3">Loading project…</div>
      </div>
    );
  }

  const hasPrev = project.previous_version_id != null;

  return (
    <div className="flex h-[calc(100vh-60px)]">
      {/* Left — chat / plans */}
      <aside className="w-[380px] shrink-0 border-r border-rule bg-paper-2 flex flex-col">
        <header className="px-4 py-3 border-b border-rule">
          <Link href="/builder" className="text-[11px] text-ink-3 hover:text-ink">
            ← All projects
          </Link>
          <div className="mt-1 font-serif text-[18px] text-ink">{project.name}</div>
          <div className="mt-0.5 text-[11px] text-ink-3">
            {project.framework} · {project.status}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {plans.length === 0 && (
            <div className="text-[13px] text-ink-3">
              Ask for anything in plain English — a new page, a design
              tweak, a data field, a fix. Builder will plan it for you.
            </div>
          )}
          {plans
            .slice()
            .reverse()
            .map((pl) => (
              <PlanTurn
                key={pl.id}
                plan={pl}
                onApprove={() => onApprove(pl.id)}
                onReject={() => onReject(pl.id)}
              />
            ))}
          <div ref={bottomRef} />
        </div>

        <footer className="border-t border-rule p-3 space-y-2">
          {error && (
            <p className="rounded-sm border border-terracotta/40 bg-terracotta/5 px-2 py-1 text-[11px] text-terracotta-2">
              {error}
            </p>
          )}
          <DailyBudgetBar project={project} />

          <textarea
            rows={2}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Add a pricing section with three tiers."
            disabled={busy}
            className="flex w-full rounded-sm border border-rule bg-paper px-3 py-2 text-[13px] text-ink placeholder:text-ink-3/80 focus-visible:outline-none focus-visible:border-ink-2 resize-none"
          />
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={onUndo}
              disabled={!hasPrev || busy}
              className={cn(
                "text-[11px]",
                hasPrev
                  ? "text-ink-3 hover:text-terracotta"
                  : "text-ink-3/50 cursor-not-allowed",
              )}
            >
              Undo last change
            </button>
            <Button
              variant="accent"
              onClick={onAsk}
              disabled={!prompt.trim() || busy}
            >
              {busy ? "Thinking…" : "Ask Builder"}
            </Button>
          </div>
        </footer>
      </aside>

      {/* Center — live preview (StackBlitz WebContainer) */}
      <main className="flex-1 relative bg-sand/40">
        <PreviewFrame projectId={id} refreshKey={previewKey} />
        <div className="absolute top-3 right-3 flex items-center gap-2 z-10">
          {verify && (
            <div
              className={cn(
                "rounded-sm border px-2 py-1 text-[10px]",
                verify.ok
                  ? "border-sage/40 bg-sage/10 text-ink"
                  : "border-terracotta/40 bg-terracotta/5 text-terracotta-2",
              )}
              title={`${verify.warnings} warning, ${verify.errors} error`}
            >
              {verify.ok ? "✓" : "⚠"} {verify.checks.length} check
              {verify.checks.length === 1 ? "" : "s"}
            </div>
          )}
          <button
            type="button"
            onClick={() => void onExportZip()}
            className="rounded-sm border border-rule bg-paper/95 px-2 py-1 text-[11px] text-ink-2 hover:bg-sand"
            title="Download the current project as a ZIP"
          >
            Export ZIP
          </button>
          <Link
            href={`/builder/${id}/publish`}
            className="rounded-sm border border-rule bg-paper/95 px-2 py-1 text-[11px] text-ink-2 hover:bg-sand"
          >
            Publish
          </Link>
          <button
            type="button"
            onClick={() => setDrawerOpen((v) => !v)}
            className="rounded-sm border border-rule bg-paper/95 px-2 py-1 text-[11px] text-ink-3 hover:bg-sand"
          >
            {drawerOpen ? "Hide files" : "Show files"}
          </button>
        </div>
      </main>

      {/* Right — collapsed file drawer */}
      {drawerOpen && (
        <aside className="w-[320px] shrink-0 border-l border-rule bg-paper-2 overflow-y-auto">
          <div className="px-4 py-3 border-b border-rule text-[10px] uppercase tracking-[0.08em] text-ink-3">
            Files
          </div>
          <ul className="py-2">
            {files.map((f) => (
              <li
                key={f.path}
                className="px-4 py-1.5 text-[12px] font-mono text-ink-2 hover:bg-sand/50"
                title={f.path}
              >
                {f.path}
              </li>
            ))}
            {files.length === 0 && (
              <li className="px-4 py-2 text-[12px] text-ink-3">
                (no files yet)
              </li>
            )}
          </ul>
        </aside>
      )}
    </div>
  );
}

function PlanTurn({
  plan,
  onApprove,
  onReject,
}: {
  plan: BuilderPlan;
  onApprove: () => void;
  onReject: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-sm border border-rule bg-paper p-3">
      <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
        You said
      </div>
      <p className="text-[13px] text-ink-2 italic mb-2">
        &ldquo;{plan.user_prompt}&rdquo;
      </p>
      <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1 flex items-center gap-2">
        <PlanStatusDot status={plan.status} />
        The plan
      </div>
      <p className="text-[13px] text-ink leading-relaxed">{plan.plain_plan}</p>

      {plan.affected_areas.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {plan.affected_areas.map((a, i) => (
            <span
              key={i}
              title={a.rationale}
              className="rounded-full border border-rule bg-paper-2 px-2 py-0.5 text-[10px] text-ink-2"
            >
              {a.label}
            </span>
          ))}
        </div>
      )}

      {plan.risks && (
        <p className="mt-2 text-[11px] text-ink-3">
          <span className="font-medium">Heads up:</span> {plan.risks}
        </p>
      )}

      {plan.status === "proposed" && (
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onReject}
            className="rounded-sm border border-rule bg-paper px-2.5 py-1 text-[11px] text-ink-2 hover:bg-sand"
          >
            Not this one
          </button>
          <button
            type="button"
            onClick={onApprove}
            className="rounded-sm border border-ink bg-ink px-3 py-1 text-[11px] text-paper hover:bg-terracotta hover:border-terracotta"
          >
            Looks good — apply
          </button>
        </div>
      )}

      {plan.status === "applied" && (
        <div className="mt-2 rounded-sm border border-sage/40 bg-sage/10 px-2 py-1.5 text-[11px] text-ink">
          ✓ Applied — preview updated. Use Undo in the bottom-left to
          revert if it&rsquo;s not right.
        </div>
      )}
      {plan.status === "rejected" && (
        <p className="mt-2 text-[11px] text-ink-3">Skipped.</p>
      )}
      {plan.status === "failed" && plan.error && (
        <p className="mt-2 text-[11px] text-terracotta-2">
          Couldn&rsquo;t apply: {plan.error}
        </p>
      )}

      {plan.technical_plan && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-3 text-[10px] text-ink-3 hover:text-ink"
          >
            {expanded ? "Hide" : "Show"} technical detail
          </button>
          {expanded && (
            <pre className="mt-1 whitespace-pre-wrap rounded-sm bg-paper-2 p-2 text-[10px] text-ink-3 border border-rule">
              {plan.technical_plan}
            </pre>
          )}
        </>
      )}
    </div>
  );
}

function DailyBudgetBar({ project }: { project: BuilderProject }) {
  const used = project.daily_spend_cents;
  const cap = project.daily_spend_cap_cents;
  if (!cap || cap <= 0) return null;
  const pct = Math.min(1, used / cap);
  const tone = pct >= 1 ? "rose" : pct >= 0.6 ? "amber" : "ink-3";
  return (
    <div className="text-[10px] text-ink-3">
      <div className="flex items-center justify-between">
        <span>Today&rsquo;s Builder budget</span>
        <span
          className={cn(
            "tabular",
            tone === "rose" && "text-terracotta-2",
            tone === "amber" && "text-ink",
          )}
        >
          ${(used / 100).toFixed(2)} / ${(cap / 100).toFixed(2)}
        </span>
      </div>
      <div className="mt-1 h-1 w-full rounded-full bg-sand overflow-hidden">
        <div
          className={cn(
            "h-full",
            tone === "rose"
              ? "bg-terracotta"
              : tone === "amber"
                ? "bg-amber"
                : "bg-ink-3",
          )}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
      {pct >= 1 && (
        <p className="mt-1 text-terracotta-2">
          You&rsquo;ve hit today&rsquo;s cap. New plans will resume tomorrow, or
          raise the cap in Settings.
        </p>
      )}
      {pct >= 0.6 && pct < 1 && (
        <p className="mt-1">60% of today&rsquo;s cap used — plan accordingly.</p>
      )}
    </div>
  );
}

function PlanStatusDot({ status }: { status: string }) {
  const tone =
    status === "applied"
      ? "bg-sage"
      : status === "failed"
        ? "bg-terracotta"
        : status === "rejected"
          ? "bg-sand-2"
          : "bg-amber";
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full", tone)} />;
}
