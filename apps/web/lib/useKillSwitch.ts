"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getKillSwitch, setKillSwitch } from "@/lib/api";

/**
 * Shared kill-switch client state for web screens. Refetches on every
 * route change and every 15 seconds so a toggle on one tab surfaces in
 * another within the backend's 1s TTL + our polling interval.
 */
export function useKillSwitch() {
  const [active, setActive] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pathname = usePathname();

  const refresh = useCallback(async () => {
    try {
      const s = await getKillSwitch();
      setActive(s.active);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 15_000);
    return () => clearInterval(t);
  }, [refresh, pathname]);

  const toggle = useCallback(async (next: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const s = await setKillSwitch(next);
      setActive(s.active);
      return s.active;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      throw e;
    } finally {
      setBusy(false);
    }
  }, []);

  return { active, busy, error, refresh, toggle };
}
