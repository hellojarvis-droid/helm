import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { getKillSwitch, setKillSwitch } from "./api";

/**
 * Shared kill-switch state for mobile screens. Every tab that wants to
 * reflect the current PAUSE_ALL_AGENTS state calls this and re-fetches on
 * focus — cheap, and matches the backend's 1s TTL cache so we never see
 * stale state for long.
 */
export function useKillSwitch() {
  const [active, setActive] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await getKillSwitch();
      setActive(s.active);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );

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
