"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createGeneration,
  getGeneration,
  InsufficientCreditsError,
  listGenerations,
  listModels,
  runGenerationAction,
  toggleFavoriteGeneration,
  type CanvasTool,
  type Generation,
  type ModelEntry,
  type ReferenceChipT,
} from "@/lib/api";

// Shared hook every Canvas tool uses. Keeps:
//   * session_id (client-generated UUID, persisted per-tool in
//     localStorage so reloads resume the session)
//   * models list + selected model
//   * in-flight + finished generations for the session
//   * poll loop that advances running gens to terminal
//   * createGeneration wrapper that handles 402 InsufficientCredits
//   * action chips → spawn follow-up generations

interface Options {
  tool: CanvasTool;
  businessId: string | null;
}

const SESSION_KEY = (tool: CanvasTool) => `helm:studio:session:${tool}`;

function newUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function useGenerationSession({ tool, businessId }: Options) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [modelSlug, setModelSlug] = useState<string>("");
  const [gens, setGens] = useState<Generation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Init session id from localStorage.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const key = SESSION_KEY(tool);
    let saved = window.localStorage.getItem(key);
    if (!saved) {
      saved = newUuid();
      window.localStorage.setItem(key, saved);
    }
    setSessionId(saved);
  }, [tool]);

  // Load models for this tool.
  useEffect(() => {
    (async () => {
      try {
        const list = await listModels(tool);
        setModels(list);
        if (!modelSlug && list.length) {
          const rec = list.find((m) => m.recommended_for.includes(tool));
          const chosen = rec ?? list[0];
          if (chosen) setModelSlug(chosen.slug);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [tool, modelSlug]);

  // Load generations for the session.
  const refresh = useCallback(async () => {
    if (!sessionId) return;
    try {
      const rows = await listGenerations({ session_id: sessionId });
      setGens(rows);
    } catch {
      // swallow — auth blip
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while anything is in-flight.
  useEffect(() => {
    const anyRunning = gens.some((g) =>
      g.status === "queued" || g.status === "running" || g.status === "pending",
    );
    if (anyRunning) {
      pollRef.current = setInterval(() => void refresh(), 4000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [gens, refresh]);

  const resetSession = () => {
    if (typeof window === "undefined") return;
    const fresh = newUuid();
    window.localStorage.setItem(SESSION_KEY(tool), fresh);
    setSessionId(fresh);
    setGens([]);
  };

  const selectedModel = models.find((m) => m.slug === modelSlug);

  const generate = async (opts: {
    prompt: string;
    params: Record<string, unknown>;
    references?: ReferenceChipT[];
  }) => {
    if (!sessionId || !modelSlug) return;
    setBusy(true);
    setError(null);
    try {
      const g = await createGeneration({
        business_id: businessId,
        session_id: sessionId,
        tool,
        model: modelSlug,
        prompt: opts.prompt,
        params: opts.params,
        references: opts.references ?? [],
      });
      setGens((prev) => [g, ...prev]);
    } catch (e) {
      if (e instanceof InsufficientCreditsError) {
        setError(
          `Not enough credits — need $${(e.needed_cents / 100).toFixed(2)}, balance $${(e.balance_cents / 100).toFixed(2)}. Top up via the chip in the topbar.`,
        );
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const action = async (
    genId: string,
    kind: "animate" | "lipsync" | "edit" | "upscale" | "use_as_reference",
  ) => {
    setError(null);
    try {
      const next = await runGenerationAction(genId, { action: kind });
      if (kind === "use_as_reference") {
        // Caller uses the returned URL as a new ref; nothing new to append.
        return next;
      }
      setGens((prev) => [next, ...prev]);
      return next;
    } catch (e) {
      if (e instanceof InsufficientCreditsError) {
        setError(
          `Not enough credits — need $${(e.needed_cents / 100).toFixed(2)}.`,
        );
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
      return null;
    }
  };

  const toggleFavorite = async (genId: string) => {
    try {
      const next = await toggleFavoriteGeneration(genId);
      setGens((prev) => prev.map((g) => (g.id === genId ? next : g)));
    } catch {
      // ignore
    }
  };

  const refreshGen = async (genId: string) => {
    try {
      const next = await getGeneration(genId);
      setGens((prev) => prev.map((g) => (g.id === genId ? next : g)));
    } catch {
      // ignore
    }
  };

  return {
    sessionId,
    resetSession,
    models,
    selectedModel,
    modelSlug,
    setModelSlug,
    gens,
    busy,
    error,
    setError,
    generate,
    action,
    toggleFavorite,
    refresh,
    refreshGen,
  };
}
