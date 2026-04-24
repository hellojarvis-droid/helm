"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { listBuilderProjects, type BuilderProject } from "@/lib/api";

export default function BuilderHome() {
  const [rows, setRows] = useState<BuilderProject[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setRows(await listBuilderProjects());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-[36px] leading-none tracking-tightest text-ink">
            Builder
          </h1>
          <p className="mt-2 max-w-[60ch] text-[14px] text-ink-2">
            Describe what you want in plain English — Builder turns it
            into a real product. Start from scratch, import an existing
            site, or edit what&rsquo;s already there.
          </p>
        </div>
        <Link href="/builder/new">
          <Button variant="accent" size="lg">
            + New project
          </Button>
        </Link>
      </header>

      {error && (
        <div className="mb-6 rounded-sm border border-terracotta/40 bg-terracotta/5 px-4 py-3 text-[13px] text-terracotta-2">
          {error}
        </div>
      )}

      {!hydrated ? (
        <div className="text-[13px] text-ink-3">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="rounded-sm border border-rule bg-paper-2 p-8 text-center">
          <div className="font-serif text-[22px] text-ink mb-2">
            Your first project starts with a sentence.
          </div>
          <p className="text-[13px] text-ink-2 mb-4 max-w-[46ch] mx-auto">
            Try something like &ldquo;a landing page for my coffee
            subscription&rdquo; or paste a GitHub URL to pick up where
            you left off.
          </p>
          <Link href="/builder/new">
            <Button variant="accent">Start a new project</Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {rows.map((p) => (
            <Link
              key={p.id}
              href={`/builder/${p.id}`}
              className="group rounded-sm border border-rule bg-paper-2 p-4 hover:border-ink hover:bg-paper transition-colors"
            >
              <div className="flex items-center gap-1.5 mb-1.5 text-[10px] uppercase tracking-[0.06em] text-ink-3">
                <StatusDot status={p.status} />
                {p.status}
                <span className="text-ink-3/60">· {p.framework}</span>
              </div>
              <div className="font-serif text-[20px] text-ink group-hover:text-terracotta transition-colors">
                {p.name}
              </div>
              {p.description && (
                <p className="mt-1 text-[12px] text-ink-2 line-clamp-2">
                  {p.description}
                </p>
              )}
              <div className="mt-3 text-[10px] text-ink-3">
                Updated {new Date(p.updated_at).toLocaleDateString()}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const tone =
    status === "published"
      ? "bg-sage"
      : status === "error"
        ? "bg-terracotta"
        : "bg-amber";
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full", tone)} />;
}
