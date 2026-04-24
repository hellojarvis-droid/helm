"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/cn";
import type { ReferenceChipT, ReferenceRole } from "@/lib/api";

// Prompt textarea with inline reference chips (Ideogram pattern).
// Drop an image URL or paste → attach popup asks for role → chip
// renders inside the prompt container with label.

const ROLE_LABELS: Record<ReferenceRole, string> = {
  character: "Character",
  style: "Style",
  describe: "Describe",
  magic_fill: "Magic Fill",
  background_replace: "Background",
};

export function PromptBox({
  value,
  onChange,
  placeholder,
  references,
  onReferencesChange,
  disabled,
  rows = 3,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  references: ReferenceChipT[];
  onReferencesChange: (refs: ReferenceChipT[]) => void;
  disabled?: boolean;
  rows?: number;
}) {
  const [attachUrl, setAttachUrl] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const onPickFile = () => fileRef.current?.click();

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // For v1 we embed as a data URL — future work is server upload.
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") setAttachUrl(reader.result);
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const attachPaste = () => {
    const url = window.prompt("Paste image URL");
    if (url && url.trim()) setAttachUrl(url.trim());
  };

  const confirmRole = (role: ReferenceRole) => {
    if (!attachUrl) return;
    onReferencesChange([
      ...references,
      { url: attachUrl, role, label: ROLE_LABELS[role] },
    ]);
    setAttachUrl(null);
  };

  const removeRef = (idx: number) => {
    onReferencesChange(references.filter((_, i) => i !== idx));
  };

  return (
    <div className="rounded-sm border border-rule bg-paper">
      {references.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b border-rule p-2">
          {references.map((r, i) => (
            <ReferenceChip key={`${r.url}-${i}`} ref_={r} onRemove={() => removeRef(i)} />
          ))}
        </div>
      )}
      <textarea
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="flex w-full bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-ink-3/80 focus:outline-none resize-none"
      />
      <div className="flex items-center justify-between border-t border-rule px-2 py-1.5 text-[11px] text-ink-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onPickFile}
            disabled={disabled}
            className="rounded-full border border-rule bg-paper-2 px-2 py-0.5 hover:bg-sand"
          >
            + Attach image
          </button>
          <button
            type="button"
            onClick={attachPaste}
            disabled={disabled}
            className="rounded-full border border-rule bg-paper-2 px-2 py-0.5 hover:bg-sand"
          >
            + Paste URL
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            onChange={onFileChange}
            className="hidden"
          />
        </div>
        <span>{value.length} chars</span>
      </div>

      {attachUrl && (
        <div className="fixed inset-0 z-30 bg-ink/40 grid place-items-center">
          <div className="w-[420px] rounded-sm border border-rule bg-paper p-4 shadow-lg">
            <div className="text-[11px] uppercase tracking-[0.08em] text-ink-3 mb-2">
              Use this image as…
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={attachUrl}
              alt=""
              className="mb-3 max-h-[180px] w-full rounded-sm object-contain bg-sand"
            />
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(ROLE_LABELS) as ReferenceRole[]).map((role) => (
                <button
                  key={role}
                  type="button"
                  onClick={() => confirmRole(role)}
                  className="rounded-sm border border-rule bg-paper-2 px-3 py-2 text-[13px] hover:bg-sand"
                >
                  <div className="font-medium text-ink">{ROLE_LABELS[role]}</div>
                  <div className="mt-0.5 text-[10px] text-ink-3">
                    {HELP_COPY[role]}
                  </div>
                </button>
              ))}
            </div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => setAttachUrl(null)}
                className="text-[12px] text-ink-3 hover:text-ink"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const HELP_COPY: Record<ReferenceRole, string> = {
  character: "Preserve this face / subject",
  style: "Borrow this look + palette",
  describe: "Use this scene as a starting point",
  magic_fill: "Paint on this; regenerate inside",
  background_replace: "Swap the background",
};

function ReferenceChip({
  ref_,
  onRemove,
}: {
  ref_: ReferenceChipT;
  onRemove: () => void;
}) {
  return (
    <span className={cn("group inline-flex items-center gap-1.5 rounded-sm border border-rule bg-paper-2 pl-1 pr-2 py-0.5 text-[11px]")}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={ref_.url}
        alt=""
        className="h-5 w-5 rounded-sm object-cover bg-sand"
      />
      <span className="text-ink-2">{ref_.label ?? ref_.role}</span>
      <button
        type="button"
        onClick={onRemove}
        className="text-ink-3 hover:text-terracotta"
        aria-label="Remove reference"
      >
        ×
      </button>
    </span>
  );
}
