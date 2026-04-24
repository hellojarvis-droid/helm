"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/design/Icon";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
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
    <AppShell breadcrumbs={["Helm", "Safety"]}>
      <div className="px-10 pt-8 pb-20 max-w-4xl">
        <header className="mb-7">
          <div className="text-[12px] text-ink-3 tracking-[0.08em] uppercase mb-2">
            Hard rule #2 · kill switch
          </div>
          <h1
            className={cn(
              "font-serif text-[64px] leading-none tracking-tightest",
              active ? "text-rose-2" : "text-sage-2",
            )}
          >
            {active === null ? "…" : active ? "Paused" : "All systems go"}
          </h1>
          <p className="text-sm text-ink-3 mt-4 max-w-prose">
            {active
              ? "Every agent across every business is halted. No tool calls, no spend, no sends. Webhooks will log but won't act until you resume."
              : "Agents are running normally. Flip this switch to halt every tool call across every business within one second."}
          </p>
        </header>

        {error ? <p className="text-sm text-rose-2 mb-4">{error}</p> : null}

        <div className="mb-8">
          <Button
            size="lg"
            onClick={onToggle}
            disabled={busy || active === null}
            className={cn(
              active
                ? "bg-paper border-2 border-rose-2 text-rose-2 hover:bg-rose-soft"
                : "bg-rose-2 text-paper border-rose-2 hover:bg-rose-2/90",
            )}
          >
            {busy ? "…" : active ? "Resume everything" : "Pause everything"}
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-5">
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
      </div>

      {confirmOpen ? (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center p-6 z-[60]">
          <div className="bg-paper rounded-xl border-2 border-rose-2/50 p-6 max-w-md w-full shadow-lg">
            <div className="flex items-center gap-2 mb-2 text-rose-2">
              <Icon name="pause" size={18} />
              <h2 className="text-lg font-semibold">Pause every agent?</h2>
            </div>
            <p className="text-sm mb-5 text-ink-2">
              This halts every running agent across every business within one second. In-flight tool
              calls may still finish but no new ones will start. Stripe authorizations on your
              issuing card will decline until you resume.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={onConfirmPause}
                className="bg-rose-2 text-paper border-rose-2 hover:bg-rose-2/90"
              >
                Pause everything
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
