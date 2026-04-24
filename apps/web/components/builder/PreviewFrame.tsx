"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import {
  getBuilderPreviewManifest,
  type BuilderPreviewManifest,
} from "@/lib/api";

// WebContainer-hosted preview. Boots once per mount, mounts the
// project's file tree, runs `npm install` (for Vite/Next/CRA), spawns
// the framework's dev command, and shows the resulting dev-server URL
// in an iframe.
//
// Static-HTML projects short-circuit the install+dev path and render
// the raw HTML in an iframe via a blob URL.

type BootStage =
  | "idle"
  | "loading_manifest"
  | "booting_container"
  | "mounting_files"
  | "installing_deps"
  | "starting_dev"
  | "ready"
  | "static_ready"
  | "error";

export interface PreviewFrameHandle {
  reload: () => void;
}

export function PreviewFrame({
  projectId,
  refreshKey,
}: {
  projectId: string;
  refreshKey: number; // bump to re-mount (after a new plan applies)
}) {
  const [stage, setStage] = useState<BootStage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [elapsedSec, setElapsedSec] = useState(0);
  const containerRef = useRef<unknown>(null);
  const bootIdRef = useRef(0);
  const startRef = useRef<number>(0);
  // Blob URL + listener refs — using refs so tearDown reads current
  // values, not values from the closure when useCallback fired.
  const blobUrlRef = useRef<string | null>(null);
  const serverReadyOffRef = useRef<(() => void) | null>(null);

  // Boot-id guarded log writer — pipes from killed containers can flush
  // buffered bytes after teardown. Drop anything older than current.
  const appendLog = useCallback((line: string, bootId: number) => {
    if (bootId !== bootIdRef.current) return;
    setLogs((prev) => {
      const next = [...prev, line];
      return next.length > 200 ? next.slice(-200) : next;
    });
  }, []);

  const tearDown = useCallback(async () => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
    if (serverReadyOffRef.current) {
      try {
        serverReadyOffRef.current();
      } catch {
        // ignore
      }
      serverReadyOffRef.current = null;
    }
    const c = containerRef.current as { teardown?: () => Promise<void> } | null;
    if (c && typeof c.teardown === "function") {
      try {
        await c.teardown();
      } catch {
        // ignore
      }
    }
    containerRef.current = null;
  }, []);

  const boot = useCallback(async () => {
    const myBootId = ++bootIdRef.current;
    setError(null);
    setLogs([]);
    setIframeUrl(null);
    setStage("loading_manifest");
    setElapsedSec(0);
    startRef.current = Date.now();
    await tearDown();

    let manifest: BuilderPreviewManifest;
    try {
      manifest = await getBuilderPreviewManifest(projectId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStage("error");
      return;
    }
    if (myBootId !== bootIdRef.current) return;

    // Static projects: skip the entire WebContainer boot — render the
    // root index.html in an iframe via a blob URL.
    if (manifest.framework === "static" || !manifest.dev_command.length) {
      const html =
        manifest.files["index.html"] ??
        Object.entries(manifest.files).find(([p]) => p.endsWith("/index.html"))?.[1] ??
        "";
      if (!html) {
        setError(
          "No index.html in the project — ask Builder to add one to enable the preview.",
        );
        setStage("error");
        return;
      }
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      blobUrlRef.current = url;
      setIframeUrl(url);
      setStage("static_ready");
      return;
    }

    // Dynamic framework (Vite/Next/CRA): boot WebContainer.
    setStage("booting_container");

    // WebContainer needs cross-origin isolation for SharedArrayBuffer.
    // If the page isn't isolated, surface a clean actionable error
    // rather than hanging at boot().
    if (typeof window !== "undefined" && window.crossOriginIsolated === false) {
      setError(
        "Preview can't start because the page isn't cross-origin-isolated. " +
          "Hard-refresh (Cmd+Shift+R) the Builder page, then try again. " +
          "If this persists, restart the web dev server so the security headers apply.",
      );
      setStage("error");
      return;
    }

    let WebContainer: typeof import("@webcontainer/api").WebContainer;
    try {
      const mod = await import("@webcontainer/api");
      WebContainer = mod.WebContainer;
    } catch (e) {
      setError(
        "Preview requires WebContainer support — reload the Builder page and try again. " +
          (e instanceof Error ? e.message : ""),
      );
      setStage("error");
      return;
    }
    if (myBootId !== bootIdRef.current) return;

    let container: import("@webcontainer/api").WebContainer;
    try {
      // Boot can silently hang if the browser isn't cross-origin
      // isolated. Race against a 25s timeout so we surface a clean
      // error instead of spinning forever.
      container = await Promise.race([
        WebContainer.boot(),
        new Promise<never>((_, reject) =>
          setTimeout(
            () => reject(new Error("sandbox boot timed out after 25s")),
            25_000,
          ),
        ),
      ]);
      containerRef.current = container;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      const diag = browserDiagnostics();
      setError(
        `Couldn't boot the in-browser sandbox.\n\n` +
          (msg.includes("timed out")
            ? "The sandbox boot timed out.\n\n"
            : `Error: ${msg}\n\n`) +
          `Diagnostics:\n` +
          `  crossOriginIsolated: ${diag.isolated}\n` +
          `  SharedArrayBuffer: ${diag.sab}\n` +
          `  Browser: ${diag.browser}\n\n` +
          (diag.isolated
            ? "Your browser reports cross-origin isolation is active, but WebContainer still couldn't start. " +
              "Safari sometimes needs version 17+. Chrome 94+, Firefox 105+, Edge 94+ work reliably. " +
              "Try opening /builder/<project-id> in a fresh tab."
            : "Your page is NOT cross-origin isolated — that's why boot hangs. " +
              "Hard-refresh the Builder page (Cmd+Shift+R) so the security headers reload. " +
              "If the dev server needs a restart, run: `pnpm --filter @helm/web dev` again."),
      );
      setStage("error");
      return;
    }
    if (myBootId !== bootIdRef.current) return;

    setStage("mounting_files");
    try {
      await container.mount(manifestToTree(manifest.files));
    } catch (e) {
      setError("Couldn't mount the project files. " + (e instanceof Error ? e.message : ""));
      setStage("error");
      return;
    }

    setStage("installing_deps");
    try {
      const install = await container.spawn("npm", ["install", "--silent"]);
      install.output.pipeTo(
        new WritableStream({
          write(chunk) {
            appendLog(chunk, myBootId);
          },
        }),
      );
      const installCode = await install.exit;
      if (installCode !== 0) {
        setError(`Dependency install failed (exit ${installCode}).`);
        setStage("error");
        return;
      }
    } catch (e) {
      setError("Install failed. " + (e instanceof Error ? e.message : ""));
      setStage("error");
      return;
    }
    if (myBootId !== bootIdRef.current) return;

    setStage("starting_dev");

    // server-ready fires when the dev server listens on a port. Race
    // that against the dev process exit (early exit = crash) and a
    // 60s wall-clock timeout so we never spin forever.
    const serverReadyPromise = new Promise<string>((resolve) => {
      const handler = (_port: number, url: string) => {
        if (myBootId !== bootIdRef.current) return;
        resolve(url);
      };
      container.on("server-ready", handler);
      // Store a best-effort "off" — WebContainer lacks a documented
      // .off(), but teardown() should collect the handler. We wrap in a
      // no-op so `serverReadyOffRef.current()` is always callable.
      serverReadyOffRef.current = () => {};
    });

    let dev: import("@webcontainer/api").WebContainerProcess;
    try {
      dev = await container.spawn(
        manifest.dev_command[0]!,
        manifest.dev_command.slice(1),
      );
    } catch (e) {
      setError("Dev server couldn't start. " + (e instanceof Error ? e.message : ""));
      setStage("error");
      return;
    }

    let sawDevLog = "";
    dev.output.pipeTo(
      new WritableStream({
        write(chunk) {
          appendLog(chunk, myBootId);
          if (sawDevLog.length < 4000) sawDevLog += chunk;
        },
      }),
    );

    const devExitPromise = dev.exit.then((code) => {
      throw new Error(
        `Dev server exited unexpectedly with code ${code}. Recent output:\n` +
          sawDevLog.slice(-800),
      );
    });

    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(
        () =>
          reject(
            new Error(
              "Dev server didn't become ready within 60 seconds. " +
                "Last output:\n" +
                sawDevLog.slice(-800),
            ),
          ),
        60_000,
      ),
    );

    try {
      const url = await Promise.race([
        serverReadyPromise,
        devExitPromise,
        timeoutPromise,
      ]);
      if (myBootId !== bootIdRef.current) return;
      setIframeUrl(url);
      setStage("ready");
    } catch (e) {
      if (myBootId !== bootIdRef.current) return;
      setError(e instanceof Error ? e.message : String(e));
      setStage("error");
    }
  }, [projectId, appendLog, tearDown]);

  useEffect(() => {
    void boot();
    return () => {
      void tearDown();
    };
    // boot is stable via useCallback but depend on refreshKey to
    // re-mount after each applied plan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, refreshKey]);

  // Tick an elapsed counter while booting so the UI doesn't feel dead.
  useEffect(() => {
    const booting =
      stage !== "idle" &&
      stage !== "ready" &&
      stage !== "static_ready" &&
      stage !== "error";
    if (!booting) return;
    const iv = setInterval(() => {
      setElapsedSec(Math.round((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(iv);
  }, [stage]);

  return (
    <div className="relative h-full w-full">
      {iframeUrl ? (
        <iframe
          src={iframeUrl}
          title="Project preview"
          className="h-full w-full border-0 bg-paper"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        />
      ) : (
        <div className="h-full w-full grid place-items-center bg-sand/40">
          <div className="max-w-[460px] text-center p-8">
            {stage === "error" ? (
              <>
                <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-paper border border-terracotta/40 text-terracotta mb-3">
                  !
                </div>
                <h2 className="font-serif text-[20px] text-ink">
                  Preview hit a snag
                </h2>
                <pre className="mt-2 whitespace-pre-wrap text-left text-[11px] text-ink-2 font-mono bg-paper border border-rule rounded-sm p-3">
                  {error}
                </pre>
                <div className="mt-3 flex items-center justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => void boot()}
                    className="rounded-sm border border-ink bg-ink px-3 py-1 text-[11px] text-paper hover:bg-terracotta hover:border-terracotta"
                  >
                    Try again
                  </button>
                  <a
                    href={typeof window !== "undefined" ? window.location.href : "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-sm border border-rule bg-paper px-3 py-1 text-[11px] text-ink-2 hover:bg-sand"
                  >
                    Open in new tab
                  </a>
                </div>
              </>
            ) : (
              <>
                <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-paper border border-rule mb-3">
                  <Spinner />
                </div>
                <h2 className="font-serif text-[20px] text-ink">
                  {stageLabel(stage)}
                  {elapsedSec > 0 && (
                    <span className="ml-2 text-[13px] text-ink-3 tabular">
                      {elapsedSec}s
                    </span>
                  )}
                </h2>
                <p className="mt-2 text-[12px] text-ink-2">
                  {stageHint(stage)}
                </p>
                {elapsedSec > 45 && stage === "installing_deps" && (
                  <p className="mt-2 text-[11px] text-ink-3">
                    First install on a fresh project can take up to 90s.
                    Subsequent previews reuse the cache and are near-instant.
                  </p>
                )}
                {elapsedSec > 20 && stage === "booting_container" && (
                  <p className="mt-2 text-[11px] text-ink-3">
                    Still booting — if this doesn&rsquo;t clear in 30s, hard-
                    refresh (Cmd+Shift+R) to re-apply the security headers.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <LogPanel logs={logs} />

      {iframeUrl && (
        <button
          type="button"
          onClick={() => void boot()}
          className="absolute top-3 left-3 rounded-sm border border-rule bg-paper/95 px-2 py-1 text-[11px] text-ink-3 hover:bg-sand"
        >
          Reload preview
        </button>
      )}
    </div>
  );
}

function stageLabel(stage: BootStage): string {
  return {
    idle: "Getting ready…",
    loading_manifest: "Loading your project…",
    booting_container: "Booting the in-browser sandbox…",
    mounting_files: "Mounting your files…",
    installing_deps: "Installing dependencies…",
    starting_dev: "Starting the dev server…",
    ready: "Ready",
    static_ready: "Ready",
    error: "Preview unavailable",
  }[stage];
}

function stageHint(stage: BootStage): string {
  return {
    idle: "",
    loading_manifest: "",
    booting_container:
      "First boot takes 10-20 seconds. Subsequent previews are much faster.",
    mounting_files: "",
    installing_deps:
      "One-time cost — 20-45 seconds depending on how many packages.",
    starting_dev: "Almost there.",
    ready: "",
    static_ready: "",
    error: "",
  }[stage];
}

function Spinner() {
  return (
    <svg className="h-6 w-6 animate-spin text-ink-3" viewBox="0 0 24 24" fill="none">
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="3"
      />
      <path
        fill="currentColor"
        d="M12 2a10 10 0 0 1 10 10h-3a7 7 0 0 0-7-7V2z"
      />
    </svg>
  );
}

function LogPanel({ logs }: { logs: string[] }) {
  const [open, setOpen] = useState(false);
  if (logs.length === 0) return null;
  return (
    <div
      className={cn(
        "absolute bottom-0 left-0 right-0 border-t border-rule bg-paper/95 backdrop-blur",
        open ? "h-[180px]" : "h-[28px]",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full h-[28px] px-3 flex items-center justify-between text-[10px] uppercase tracking-[0.08em] text-ink-3"
      >
        <span>Logs ({logs.length})</span>
        <span>{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <pre className="h-[calc(100%-28px)] overflow-y-auto px-3 py-1 text-[10px] font-mono text-ink-3 leading-snug">
          {logs.join("")}
        </pre>
      )}
    </div>
  );
}

function browserDiagnostics(): { isolated: string; sab: string; browser: string } {
  if (typeof window === "undefined") {
    return { isolated: "unknown (SSR)", sab: "unknown (SSR)", browser: "SSR" };
  }
  const isolated = window.crossOriginIsolated === true ? "true" : String(window.crossOriginIsolated);
  const sab = typeof (window as unknown as { SharedArrayBuffer?: unknown }).SharedArrayBuffer === "function"
    ? "available"
    : "missing (requires cross-origin isolation)";
  const ua = navigator.userAgent;
  let browser = "unknown";
  const versionMatch =
    /Version\/(\d+)[\d.]+\s+Safari/.exec(ua) ??
    /Chrome\/(\d+)[\d.]+/.exec(ua) ??
    /Firefox\/(\d+)[\d.]+/.exec(ua);
  if (/Safari/.test(ua) && !/Chrome/.test(ua)) {
    browser = `Safari ${versionMatch?.[1] ?? "?"} (need 17+)`;
  } else if (/Chrome/.test(ua)) {
    browser = `Chrome ${versionMatch?.[1] ?? "?"}`;
  } else if (/Firefox/.test(ua)) {
    browser = `Firefox ${versionMatch?.[1] ?? "?"}`;
  }
  return { isolated, sab, browser };
}

// Convert flat {path: content} manifest into WebContainer's nested
// directory format: { src: { directory: { 'App.jsx': { file: { contents } } } } }.
type WCEntry =
  | { file: { contents: string } }
  | { directory: Record<string, WCEntry> };

function manifestToTree(files: Record<string, string>): Record<string, WCEntry> {
  const root: Record<string, WCEntry> = {};
  for (const [path, content] of Object.entries(files)) {
    const parts = path.split("/").filter(Boolean);
    if (parts.length === 0) continue;
    let cursor = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const seg = parts[i]!;
      const existing = cursor[seg];
      if (!existing || !("directory" in existing)) {
        cursor[seg] = { directory: {} };
      }
      cursor = (cursor[seg] as { directory: Record<string, WCEntry> }).directory;
    }
    const file = parts[parts.length - 1]!;
    cursor[file] = { file: { contents: content } };
  }
  return root;
}
