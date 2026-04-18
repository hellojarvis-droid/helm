"use client";

import { useState } from "react";
import { Nav } from "@/components/Nav";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { useKillSwitch } from "@/lib/useKillSwitch";

export default function SafetyPage() {
  const { active, busy, error, toggle } = useKillSwitch();
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function onToggle() {
    if (active === null) return;
    if (!active) {
      setConfirmOpen(true);
      return;
    }
    await toggle(false);
  }

  async function onConfirmPause() {
    setConfirmOpen(false);
    await toggle(true);
  }

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        <div>
          <div className="text-xs font-semibold tracking-widest text-iron uppercase mb-1">
            Hard rule #2
          </div>
          <h1
            className={`text-4xl font-semibold tracking-tight ${
              active ? "text-danger" : "text-success"
            }`}
          >
            {active === null ? "…" : active ? "PAUSED" : "ALL SYSTEMS GO"}
          </h1>
          <p className="text-sm text-iron mt-3 max-w-prose">
            {active
              ? "Every agent across every business is halted. No tool calls, no spend, no sends. Webhooks will log but won't act until you resume."
              : "Agents are running normally. Flip this switch to halt every tool call across every business within one second."}
          </p>
        </div>

        {error ? <p className="text-sm text-danger">{error}</p> : null}

        <div>
          <Button
            size="lg"
            onClick={onToggle}
            disabled={busy || active === null}
            className={
              active
                ? "bg-transparent border-2 border-danger text-danger hover:bg-danger/5"
                : "bg-danger text-paper hover:bg-danger/90"
            }
          >
            {busy ? "…" : active ? "Resume everything" : "Pause everything"}
          </Button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Enforcement</CardTitle>
              <CardDescription>
                Backend checks this before every tool call. Stripe authorizations on your issuing
                card decline while paused. Composio calls raise KillSwitchActivated before hitting
                any provider.
              </CardDescription>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Latency</CardTitle>
              <CardDescription>
                1-second worst case. The runtime caches with a 1s TTL and invalidates on flip, so
                the next tool call after a toggle reflects the new state.
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      </main>

      {confirmOpen ? (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-6 z-10">
          <div className="bg-paper dark:bg-ink rounded-xl border border-danger/30 p-6 max-w-md w-full">
            <h2 className="text-lg font-semibold text-danger mb-2">Pause every agent?</h2>
            <p className="text-sm mb-5">
              This halts every running agent across every business within one second. In-flight tool
              calls may still finish but no new ones will start. Stripe authorizations on your
              issuing card will decline until you resume.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button onClick={onConfirmPause} className="bg-danger text-paper hover:bg-danger/90">
                Pause everything
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
