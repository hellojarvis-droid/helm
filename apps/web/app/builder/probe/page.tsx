"use client";

// Standalone probe: boots WebContainer without any app-level state
// (no auth, no PreviewFrame). Used by a Playwright script to isolate
// whether the SDK itself works in this environment vs the PreviewFrame
// orchestration being buggy.

import { useEffect, useState } from "react";

export default function BuilderProbe() {
  const [report, setReport] = useState<Record<string, unknown>>({
    stage: "pending",
  });
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    const out: Record<string, unknown> = {};
    const t0 = Date.now();
    out.isolated = window.crossOriginIsolated;
    out.sab = typeof window.SharedArrayBuffer === "function" ? "yes" : "no";
    out.userAgent = navigator.userAgent.slice(0, 160);
    out.stage = "importing";
    setReport({ ...out, elapsedMs: Date.now() - t0 });

    (async () => {
      try {
        const push = (s: string) => setLogs((prev) => [...prev, s]);

        document.addEventListener("securitypolicyviolation", (e) => {
          const evt = e as SecurityPolicyViolationEvent;
          push(
            `[CSP] ${evt.violatedDirective} blocked ${evt.blockedURI || "(inline)"}`,
          );
        });

        const mod = await import("@webcontainer/api");
        out.stage = "imported";
        out.elapsedMs = Date.now() - t0;
        setReport({ ...out });

        const { WebContainer } = mod;
        out.stage = "booting";
        out.elapsedMs = Date.now() - t0;
        setReport({ ...out });

        const timeout = new Promise<never>((_, rej) =>
          setTimeout(() => rej(new Error("boot_timeout_30s")), 30_000),
        );
        const container = await Promise.race([WebContainer.boot(), timeout]);
        out.stage = "booted";
        out.elapsedMs = Date.now() - t0;
        setReport({ ...out });

        // Mount a minimal file tree + run a trivial node script to
        // confirm process spawning works.
        await container.mount({
          "package.json": {
            file: {
              contents: JSON.stringify({
                name: "probe",
                type: "module",
                scripts: { hello: "node -e \"console.log('hello')\"" },
              }),
            },
          },
        });
        const proc = await container.spawn("node", [
          "-e",
          "console.log('hello_from_node')",
        ]);
        let spawnOut = "";
        proc.output.pipeTo(
          new WritableStream({
            write(chunk) {
              spawnOut += chunk;
            },
          }),
        );
        const code = await proc.exit;
        out.stage = "spawn_done";
        out.spawn_exit = code;
        out.spawn_output = spawnOut.slice(0, 400);
        out.elapsedMs = Date.now() - t0;
        setReport({ ...out });

        await container.teardown();
      } catch (e) {
        const err = e as Error;
        out.stage = "error";
        out.error = err?.message ?? String(err);
        out.stack = err?.stack?.slice(0, 2000);
        out.elapsedMs = Date.now() - t0;
        setReport({ ...out });
      }
    })();
  }, []);

  return (
    <div className="p-8 font-mono text-[12px]">
      <h1 className="text-[20px] font-serif mb-3">Builder probe</h1>
      <pre
        id="probe-report"
        className="bg-paper-2 border border-rule p-3 whitespace-pre-wrap"
      >
        {JSON.stringify(report, null, 2)}
      </pre>
      {logs.length > 0 && (
        <pre className="mt-3 bg-paper-2 border border-rule p-3 whitespace-pre-wrap">
          {logs.join("\n")}
        </pre>
      )}
    </div>
  );
}
