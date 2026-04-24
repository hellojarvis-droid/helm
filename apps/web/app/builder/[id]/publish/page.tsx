"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import {
  getBuilderProject,
  publishBuilderProject,
  setBuilderCustomDomain,
  type BuilderCustomDomainResponse,
  type BuilderProject,
} from "@/lib/api";
import { clientEnv } from "@/lib/env";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function PublishPanel({ params }: PageProps) {
  const { id } = use(params);
  const [project, setProject] = useState<BuilderProject | null>(null);
  const [busy, setBusy] = useState<"publish" | "domain" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customDomain, setCustomDomain] = useState("");
  const [domainResponse, setDomainResponse] =
    useState<BuilderCustomDomainResponse | null>(null);

  const refresh = useCallback(async () => {
    try {
      const p = await getBuilderProject(id);
      setProject(p);
      if (p.custom_domain) setCustomDomain(p.custom_domain);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onPublish = async () => {
    setBusy("publish");
    setError(null);
    try {
      await publishBuilderProject(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const onSetDomain = async () => {
    if (!customDomain.trim()) return;
    setBusy("domain");
    setError(null);
    try {
      const r = await setBuilderCustomDomain(id, customDomain.trim());
      setDomainResponse(r);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!project) {
    return (
      <div className="mx-auto max-w-[780px] px-8 py-10">
        <div className="text-[13px] text-ink-3">Loading project…</div>
      </div>
    );
  }

  const apiBase = clientEnv().NEXT_PUBLIC_HELM_API_BASE;
  const publishedFullUrl = project.published_url
    ? apiBase.replace(/\/$/, "") + project.published_url
    : null;

  return (
    <div className="mx-auto max-w-[780px] px-8 py-10">
      <Link
        href={`/builder/${id}`}
        className="text-[12px] text-ink-3 hover:text-ink"
      >
        ← Back to {project.name}
      </Link>
      <h1 className="mt-3 font-serif text-[32px] leading-none text-ink">Launch</h1>
      <p className="mt-2 max-w-[60ch] text-[14px] text-ink-2">
        Publish to a Helm-hosted URL anyone can open, or point your own
        domain at it. You can publish as many times as you like — the
        latest version replaces the live one.
      </p>

      {error && (
        <div className="mt-4 rounded-sm border border-terracotta/40 bg-terracotta/5 px-4 py-3 text-[13px] text-terracotta-2">
          {error}
        </div>
      )}

      <section className="mt-6 rounded-sm border border-rule bg-paper p-5">
        <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-2">
          Helm-hosted URL
        </div>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="font-mono text-[13px] text-ink truncate">
              {publishedFullUrl ?? `${apiBase}/apps/${project.slug}`}
            </div>
            <div className="mt-1 text-[11px] text-ink-3">
              {project.status === "published"
                ? "Live — click Publish again to push your latest changes."
                : "Not published yet."}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {publishedFullUrl && (
              <a
                href={publishedFullUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-sm border border-rule bg-paper-2 px-3 py-1 text-[12px] text-ink-2 hover:bg-sand"
              >
                Open →
              </a>
            )}
            <Button
              variant="accent"
              onClick={onPublish}
              disabled={busy === "publish"}
            >
              {busy === "publish"
                ? "Publishing…"
                : project.status === "published"
                  ? "Publish latest"
                  : "Publish"}
            </Button>
          </div>
        </div>
      </section>

      <section className="mt-4 rounded-sm border border-rule bg-paper p-5">
        <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-2">
          Custom domain
        </div>
        <p className="text-[12px] text-ink-2 mb-3 max-w-[56ch]">
          Use your own domain for the published project. We&rsquo;ll
          give you the DNS record to add. Automatic certificate
          provisioning is rolling out — for now reach out to support
          after you set the DNS and we&rsquo;ll flip the cert on.
        </p>
        <div className="flex items-center gap-2">
          <Input
            type="text"
            value={customDomain}
            onChange={(e) => setCustomDomain(e.target.value)}
            placeholder="app.yourbrand.com"
            disabled={busy === "domain"}
          />
          <Button
            variant="outline"
            onClick={onSetDomain}
            disabled={!customDomain.trim() || busy === "domain"}
          >
            {busy === "domain" ? "Saving…" : "Set domain"}
          </Button>
        </div>

        {(domainResponse || project.custom_domain) && (
          <DomainCard
            response={domainResponse}
            fallbackDomain={project.custom_domain}
          />
        )}
      </section>

      <section className="mt-4 rounded-sm border border-rule bg-paper-2 p-4 text-[11px] text-ink-3">
        <div className="uppercase tracking-[0.08em] mb-1 text-ink-3">
          Good to know
        </div>
        <ul className="space-y-1">
          <li>· Static HTML projects publish instantly.</li>
          <li>
            · React + Vite projects publish the source files — for now
            the preview is your source of truth; an automated build
            step lands in a follow-up.
          </li>
          <li>· Every publish replaces the live version. Your previous version is still restorable via Undo.</li>
        </ul>
      </section>
    </div>
  );
}

function DomainCard({
  response,
  fallbackDomain,
}: {
  response: BuilderCustomDomainResponse | null;
  fallbackDomain: string | null;
}) {
  const domain = response?.domain ?? fallbackDomain;
  if (!domain) return null;
  const target = response?.target ?? "cname.helm.app";
  const recordType = response?.record_type ?? "CNAME";
  return (
    <div className={cn("mt-3 rounded-sm border border-rule bg-paper-2 p-3 text-[12px]")}>
      <div className="text-ink font-medium mb-1">{domain}</div>
      <div className="text-[11px] text-ink-3">DNS record to add:</div>
      <pre className="mt-1 rounded-sm bg-paper border border-rule p-2 font-mono text-[11px]">
{`Type:  ${recordType}
Host:  ${domain}
Value: ${target}`}
      </pre>
      <div className="mt-2 text-[11px] text-ink-3">
        {response?.guidance ??
          `Add the CNAME record above with your DNS provider. Once it propagates, let us know and we'll issue the certificate.`}
      </div>
    </div>
  );
}
