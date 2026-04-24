"use client";

import Link from "next/link";

const SECTIONS = [
  {
    label: "Characters",
    href: "/studio/library/characters",
    glyph: "☺",
    desc: "Trained identities you can reuse across images and videos.",
  },
  {
    label: "Styles",
    href: "/studio/library/styles",
    glyph: "✧",
    desc: "Moodboards and style references, one-click attachable to any prompt.",
  },
  {
    label: "Presets",
    href: "/studio/library/presets",
    glyph: "◧",
    desc: "Saved generation configs — model + params + optional prompt.",
  },
  {
    label: "Assets",
    href: "/studio/library/assets",
    glyph: "▦",
    desc: "Every generation you\u2019ve ever made, searchable.",
  },
];

export default function LibraryHome() {
  return (
    <div className="max-w-[900px] mx-auto px-8 py-10">
      <header className="mb-6">
        <h1 className="font-serif text-[32px] leading-none text-ink">Library</h1>
        <p className="mt-2 text-[14px] text-ink-2">
          Reusable pieces of your creative system. Pulls from every
          business you own.
        </p>
      </header>
      <div className="grid grid-cols-2 gap-3">
        {SECTIONS.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            className="group rounded-sm border border-rule bg-paper-2 p-4 hover:border-ink hover:bg-paper transition-colors"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className="inline-flex h-7 w-7 items-center justify-center rounded-sm bg-paper border border-rule text-terracotta group-hover:border-terracotta"
                aria-hidden
              >
                {s.glyph}
              </span>
              <div className="font-medium text-[14px] text-ink">{s.label}</div>
            </div>
            <p className="text-[12px] text-ink-2 leading-relaxed">{s.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
