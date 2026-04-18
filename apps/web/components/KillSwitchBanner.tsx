"use client";

import Link from "next/link";
import { useKillSwitch } from "@/lib/useKillSwitch";

/**
 * Top-of-page banner shown whenever the kill switch is active. Keeps the
 * "everything's halted" state impossible to miss regardless of which
 * surface the user is on — CLAUDE.md hard rule #2 demands visibility.
 */
export function KillSwitchBanner() {
  const { active } = useKillSwitch();
  if (!active) return null;
  return (
    <div className="bg-danger text-paper px-6 py-2 text-sm font-medium flex items-center justify-between">
      <span>● All agents paused — no tool calls, no spend, no sends.</span>
      <Link href="/safety" className="underline underline-offset-2 hover:opacity-80">
        Open Safety →
      </Link>
    </div>
  );
}
