"use client";

import Link from "next/link";
import { useState } from "react";
import { ConnectorLogo } from "@/components/connections/ConnectorLogo";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  type ConnectionStatus,
  type ConnectorInfo,
  saveAccountApiKey,
  startAccountOAuth,
} from "@/lib/api";

// Scope-agnostic connection status. Lets us reuse the sheet for both
// /connections (account-level) and /businesses/[id]/integrations.
export interface SheetConnection {
  status: "pending" | "active" | "failed" | "expired";
  has_api_key: boolean;
  masked_key: string | null;
}

interface Props {
  connector: ConnectorInfo;
  connection: SheetConnection | null;
  // Scope title tag shown next to the category chip, e.g.
  // "Account-wide" or "Olivine Goods · per-business".
  scopeLabel?: string;
  // Scope-specific actions. Default to account-scoped handlers so the
  // existing /connections page keeps working with no arg changes.
  onSaveApiKey?: (slug: string, apiKey: string) => Promise<unknown>;
  onStartOauth?: (slug: string) => Promise<{ redirect_url: string }>;
  onClose: () => void;
  onChanged: () => void | Promise<void>;
}

export function ConnectSheet({
  connector,
  connection,
  scopeLabel,
  onSaveApiKey,
  onStartOauth,
  onClose,
  onChanged,
}: Props) {
  const connected = connection?.status === "active";
  const saveApiKey = onSaveApiKey ?? saveAccountApiKey;
  const startOauth = onStartOauth ?? startAccountOAuth;
  return (
    <div
      className="fixed inset-0 z-[60] bg-ink/40 backdrop-blur-sm grid place-items-center p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="bg-paper rounded-xl border border-rule shadow-lg w-full max-w-xl p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-5">
          <ConnectorLogo connector={connector} />
          <div className="flex-1 min-w-0">
            <h2 className="text-[18px] font-semibold">{connector.name}</h2>
            <p className="text-sm text-ink-3 mt-0.5">{connector.description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-7 w-7 grid place-items-center rounded-sm text-ink-3 hover:bg-sand hover:text-ink"
            aria-label="Close"
          >
            <Icon name="close" size={12} />
          </button>
        </div>

        <div className="flex flex-wrap gap-2 text-[11px] text-ink-3 uppercase tracking-[0.06em] mb-5">
          <span className="px-2 py-1 rounded-full bg-sand">{connector.category}</span>
          <span className="px-2 py-1 rounded-full bg-sand">
            {connector.auth_mode === "api_key" ? "Paste an API key" : "OAuth via Composio"}
          </span>
          {scopeLabel && <span className="px-2 py-1 rounded-full bg-sand">{scopeLabel}</span>}
          {connector.cost_hint && (
            <span className="px-2 py-1 rounded-full bg-sand">{connector.cost_hint}</span>
          )}
        </div>

        {connector.auth_mode === "api_key" ? (
          <ApiKeyForm
            connector={connector}
            connection={connection}
            onSave={saveApiKey}
            onClose={onClose}
            onChanged={onChanged}
          />
        ) : (
          <OauthForm
            connector={connector}
            connected={connected}
            onStart={startOauth}
            onClose={onClose}
          />
        )}

        {connector.signup_url && (
          <div className="mt-6 pt-5 border-t border-rule text-[12px] text-ink-3">
            Don&apos;t have a {connector.name} account yet?{" "}
            <Link
              href={connector.signup_url}
              target="_blank"
              rel="noreferrer noopener"
              className="text-terracotta-2 hover:underline"
            >
              Sign up at {new URL(connector.signup_url).host.replace(/^www\./, "")} →
            </Link>
          </div>
        )}

        <p className="mt-4 text-[11px] text-ink-3 leading-relaxed">
          Helm encrypts pasted keys at rest and never sends them anywhere except to{" "}
          {connector.name}. Your {connector.name} account is billed directly for usage — we
          display cost estimates in the Creative Studio so you know what each render will run.
        </p>
      </div>
    </div>
  );
}

// Legacy export name kept for existing callers.
export type { ConnectionStatus };

function ApiKeyForm({
  connector,
  connection,
  onSave,
  onClose,
  onChanged,
}: {
  connector: ConnectorInfo;
  connection: SheetConnection | null;
  onSave: (slug: string, apiKey: string) => Promise<unknown>;
  onClose: () => void;
  onChanged: () => void | Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const hasExisting = connection?.has_api_key === true;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) {
      setErr("Paste your API key first.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSave(connector.slug, value.trim());
      await onChanged();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      {hasExisting && (
        <div className="rounded-sm border border-sage/50 bg-sage-soft/50 px-3 py-2.5 text-[12.5px] text-sage-2">
          Currently connected · {connection?.masked_key}. Pasting a new key overwrites it.
        </div>
      )}
      <div className="space-y-1.5">
        <label className="text-[11px] uppercase tracking-[0.06em] text-ink-3 font-medium">
          API key
        </label>
        <Input
          type="password"
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={hasExisting ? "Paste a new key to replace" : "sk_live_…"}
          autoFocus
        />
        {connector.connect_hint && (
          <p className="text-[11.5px] text-ink-3 leading-relaxed">{connector.connect_hint}</p>
        )}
      </div>

      {err && <p className="text-sm text-rose-2">{err}</p>}

      <div className="flex gap-2 justify-end pt-2">
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" variant="accent" disabled={busy}>
          {busy ? "Saving…" : hasExisting ? "Replace key" : "Connect"}
        </Button>
      </div>
    </form>
  );
}

function OauthForm({
  connector,
  connected,
  onStart,
  onClose,
}: {
  connector: ConnectorInfo;
  connected: boolean;
  onStart: (slug: string) => Promise<{ redirect_url: string }>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setErr(null);
    try {
      const resp = await onStart(connector.slug);
      // Composio OAuth is expected to open in a new tab; the user returns to
      // Helm after and the Composio webhook flips the connection to active.
      window.open(resp.redirect_url, "_blank", "noopener,noreferrer");
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2 leading-relaxed">
        Helm opens {connector.name}&apos;s authorization page in a new tab. Grant Helm the
        scopes it asks for, and when you&apos;re back this connection flips to connected.
      </p>
      {connected && (
        <div className="rounded-sm border border-sage/50 bg-sage-soft/50 px-3 py-2.5 text-[12.5px] text-sage-2">
          Already connected. Reconnecting refreshes the OAuth token.
        </div>
      )}
      {err && <p className="text-sm text-rose-2">{err}</p>}
      <div className="flex gap-2 justify-end pt-2">
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button type="button" variant="accent" onClick={go} disabled={busy}>
          {busy ? "Opening…" : connected ? "Reconnect" : "Connect with OAuth"}
        </Button>
      </div>
    </div>
  );
}

