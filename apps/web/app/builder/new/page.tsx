"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  createBuilderProject,
  type BuilderSourceType,
} from "@/lib/api";

// Beginner-first wizard: one screen, three choices.

type Choice = "blank" | "github" | "zip";

export default function NewBuilderProject() {
  const router = useRouter();
  const [choice, setChoice] = useState<Choice>("blank");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState<"vite_react" | "static">("vite_react");
  const [sourceUrl, setSourceUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canGo =
    name.trim().length > 0 &&
    (choice !== "github" || sourceUrl.trim().length > 0);

  const run = async () => {
    setErr(null);
    setBusy(true);
    try {
      const source_type: BuilderSourceType =
        choice === "github"
          ? "import_github"
          : choice === "zip"
            ? "import_zip"
            : "blank";
      const proj = await createBuilderProject({
        name: name.trim(),
        description: description.trim() || undefined,
        source_type,
        source_url: sourceUrl.trim() || undefined,
        template,
      });
      router.push(`/builder/${proj.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-[780px] px-8 py-10">
      <Link href="/builder" className="text-[12px] text-ink-3 hover:text-ink">
        ← Back to Builder
      </Link>
      <h1 className="mt-3 font-serif text-[32px] leading-none text-ink">
        New project
      </h1>
      <p className="mt-2 text-[14px] text-ink-2 max-w-[56ch]">
        Pick a starting point. You can change anything later in plain
        English.
      </p>

      {err && (
        <div className="mt-5 rounded-sm border border-terracotta/40 bg-terracotta/5 px-4 py-3 text-[13px] text-terracotta-2">
          {err}
        </div>
      )}

      <div className="mt-6 grid grid-cols-3 gap-3">
        <ChoiceCard
          active={choice === "blank"}
          onClick={() => setChoice("blank")}
          title="Start blank"
          body="A clean site ready to shape."
        />
        <ChoiceCard
          active={choice === "github"}
          onClick={() => setChoice("github")}
          title="From GitHub"
          body="Pick up an existing project by URL."
        />
        <ChoiceCard
          active={choice === "zip"}
          onClick={() => setChoice("zip")}
          title="Upload a ZIP"
          body="Drop in a folder you already have."
        />
      </div>

      <div className="mt-6 space-y-4">
        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
            Project name
          </div>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Linen Goods site"
            disabled={busy}
          />
        </label>
        <label className="block">
          <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
            In a sentence, what is it?
          </div>
          <textarea
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A DTC linen brand landing page with a hero, product grid, and newsletter signup."
            disabled={busy}
            className="flex w-full rounded-sm border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-3/80 focus-visible:outline-none focus-visible:border-ink-2"
          />
        </label>

        {choice === "blank" && (
          <div>
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
              Template
            </div>
            <div className="flex gap-2">
              {(["vite_react", "static"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTemplate(t)}
                  disabled={busy}
                  className={cn(
                    "rounded-sm border px-3 py-1.5 text-[12px]",
                    template === t
                      ? "bg-ink text-paper border-ink"
                      : "bg-paper text-ink-2 border-rule hover:bg-sand",
                  )}
                >
                  {t === "vite_react" ? "React + Vite" : "Static HTML"}
                </button>
              ))}
            </div>
          </div>
        )}

        {choice === "github" && (
          <label className="block">
            <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3 mb-1">
              GitHub project URL
            </div>
            <Input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://github.com/yourname/your-repo"
              disabled={busy}
            />
            <p className="mt-1 text-[11px] text-ink-3">
              Works today for any public project on GitHub. Private
              projects need the GitHub connection (rolling out next).
            </p>
          </label>
        )}

        {choice === "zip" && (
          <ZipUploadBlock
            name={name}
            description={description}
            disabled={busy}
            onUploaded={(projectId) =>
              router.push(`/builder/${projectId}` as never)
            }
          />
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          <Link href="/builder" className="text-[12px] text-ink-3 hover:text-ink">
            Cancel
          </Link>
          <Button variant="accent" onClick={run} disabled={!canGo || busy}>
            {busy ? "Creating…" : "Create project"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ZipUploadBlock({
  name,
  description,
  disabled,
  onUploaded,
}: {
  name: string;
  description: string;
  disabled: boolean;
  onUploaded: (projectId: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const upload = async () => {
    if (!file || !name.trim()) {
      setErr("Pick a ZIP file and give the project a name first.");
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      const { apiFetch } = await import("@/lib/api");
      const fd = new FormData();
      fd.append("name", name.trim());
      if (description.trim()) fd.append("description", description.trim());
      fd.append("file", file, file.name);
      const res = await apiFetch(`/builder/import/zip`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`import failed: ${res.status} ${text.slice(0, 200)}`);
      }
      const proj = (await res.json()) as { id: string };
      onUploaded(proj.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-sm border border-rule bg-paper-2 px-4 py-3 space-y-3">
      <div className="text-[11px] uppercase tracking-[0.06em] text-ink-3">
        ZIP upload
      </div>
      <input
        type="file"
        accept=".zip,application/zip"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        disabled={disabled || busy}
        className="text-[12px]"
      />
      <p className="text-[11px] text-ink-3">
        Up to 40MB. We&rsquo;ll skip node_modules, .git, binaries, and
        lockfiles automatically.
      </p>
      {err && (
        <p className="rounded-sm border border-terracotta/40 bg-terracotta/5 px-2 py-1 text-[11px] text-terracotta-2">
          {err}
        </p>
      )}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={upload}
          disabled={!file || busy || disabled}
          className="rounded-sm border border-ink bg-ink px-3 py-1 text-[12px] text-paper hover:bg-terracotta hover:border-terracotta disabled:opacity-50"
        >
          {busy ? "Uploading…" : "Upload + create project"}
        </button>
      </div>
    </div>
  );
}

function ChoiceCard({
  active,
  onClick,
  title,
  body,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  body: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-sm border p-4 text-left transition-colors",
        active
          ? "border-ink bg-paper"
          : "border-rule bg-paper-2 hover:border-ink-2 hover:bg-sand",
      )}
    >
      <div className="font-medium text-[14px] text-ink">{title}</div>
      <div className="mt-1 text-[11px] text-ink-3">{body}</div>
    </button>
  );
}
