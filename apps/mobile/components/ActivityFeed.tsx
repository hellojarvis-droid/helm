import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { listEvents, type AgentEvent } from "@/lib/api";
import { colors } from "@/lib/colors";

const PAGE_SIZE = 30;

type Badge = { label: string; bg: string; fg: string; border?: string };

const BADGE: Record<string, Badge> = {
  "message.user": { label: "user", bg: colors.ink, fg: colors.paper },
  "message.agent": {
    label: "agent",
    bg: colors.haze,
    fg: colors.ink,
    border: "rgba(107,107,107,0.2)",
  },
  tool_call: {
    label: "tool",
    bg: "rgba(232,93,26,0.1)",
    fg: colors.accent,
    border: "rgba(232,93,26,0.3)",
  },
  tool_result: {
    label: "result",
    bg: "rgba(232,93,26,0.1)",
    fg: colors.accent,
    border: "rgba(232,93,26,0.3)",
  },
  approval_requested: {
    label: "approval",
    bg: "rgba(184,134,11,0.12)",
    fg: colors.warning,
    border: "rgba(184,134,11,0.35)",
  },
  approval_approved: {
    label: "approved",
    bg: "rgba(45,134,89,0.12)",
    fg: colors.success,
    border: "rgba(45,134,89,0.4)",
  },
  approval_modified: {
    label: "modified",
    bg: "rgba(232,93,26,0.1)",
    fg: colors.accent,
    border: "rgba(232,93,26,0.4)",
  },
  approval_denied: {
    label: "denied",
    bg: "rgba(168,37,26,0.1)",
    fg: colors.danger,
    border: "rgba(168,37,26,0.35)",
  },
  spend_intent: {
    label: "intent",
    bg: colors.haze,
    fg: colors.iron,
    border: "rgba(107,107,107,0.2)",
  },
  spend_authorized: {
    label: "spend",
    bg: "rgba(45,134,89,0.12)",
    fg: colors.success,
    border: "rgba(45,134,89,0.4)",
  },
  spend_declined: {
    label: "declined",
    bg: "rgba(168,37,26,0.1)",
    fg: colors.danger,
    border: "rgba(168,37,26,0.35)",
  },
  revenue_received: { label: "revenue", bg: colors.success, fg: colors.paper },
  specialist_completed: {
    label: "specialist",
    bg: colors.haze,
    fg: colors.ink,
    border: "rgba(107,107,107,0.2)",
  },
  kill_switch_activated: { label: "kill switch", bg: colors.danger, fg: colors.paper },
  error: {
    label: "error",
    bg: "rgba(168,37,26,0.1)",
    fg: colors.danger,
    border: "rgba(168,37,26,0.35)",
  },
};

export function ActivityFeed({ businessId }: { businessId: string }) {
  const [events, setEvents] = useState<AgentEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reachedEnd, setReachedEnd] = useState(false);

  const load = useCallback(
    async (beforeId?: number) => {
      setLoading(true);
      setError(null);
      try {
        const rows = await listEvents(businessId, { limit: PAGE_SIZE, beforeId });
        if (rows.length < PAGE_SIZE) setReachedEnd(true);
        setEvents((prev) => (prev ? [...prev, ...rows] : rows));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [businessId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (events === null) {
    return <ActivityIndicator style={{ marginVertical: 20 }} color={colors.iron} />;
  }

  if (error && events.length === 0) {
    return <Text style={styles.errorText}>{error}</Text>;
  }

  if (events.length === 0) {
    return (
      <Text style={styles.muted}>
        No activity yet. Events appear here as soon as the CEO Agent starts working.
      </Text>
    );
  }

  const oldestId = events[events.length - 1]?.id;

  return (
    <View style={{ gap: 2 }}>
      {events.map((ev) => (
        <EventRow key={ev.id} ev={ev} />
      ))}
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      {reachedEnd ? (
        <Text style={styles.endMarker}>— end of log —</Text>
      ) : (
        <Pressable
          onPress={() => oldestId && void load(oldestId)}
          disabled={loading}
          style={styles.loadMore}
        >
          <Text style={styles.loadMoreText}>{loading ? "Loading…" : "Load older"}</Text>
        </Pressable>
      )}
    </View>
  );
}

function EventRow({ ev }: { ev: AgentEvent }) {
  const badge = BADGE[ev.event_type] ?? {
    label: ev.event_type,
    bg: colors.haze,
    fg: colors.iron,
    border: "rgba(107,107,107,0.2)",
  };
  const when = new Date(ev.created_at).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
  const summary = summarize(ev);
  return (
    <View style={styles.row}>
      <View
        style={[styles.badge, { backgroundColor: badge.bg, borderColor: badge.border ?? badge.bg }]}
      >
        <Text style={[styles.badgeText, { color: badge.fg }]}>{badge.label}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.summary} numberOfLines={3}>
          {summary}
        </Text>
        <View style={styles.metaRow}>
          <Text style={styles.meta}>{ev.agent_name}</Text>
          <Text style={styles.meta}>{when}</Text>
          {ev.cost_cents > 0 ? <Text style={styles.meta}>{ev.cost_cents}¢</Text> : null}
        </View>
      </View>
    </View>
  );
}

function summarize(ev: AgentEvent): string {
  const p = ev.payload;
  switch (ev.event_type) {
    case "message.user":
    case "message.agent":
      return typeof p.text === "string" ? p.text : JSON.stringify(p);
    case "tool_call":
      return `Called ${stringOr(p.name, "tool")}`;
    case "tool_result":
      return `${stringOr(p.name, "tool")} → ${p.is_error ? "error" : "ok"}`;
    case "approval_requested":
      return `Requested approval: ${stringOr(p.summary, stringOr(p.kind, "—"))}`;
    case "approval_approved":
    case "approval_denied":
      return `${stringOr(p.kind, "approval")} ${
        ev.event_type === "approval_approved" ? "approved" : "denied"
      }`;
    case "approval_modified": {
      const cap = p.cap_raise as Record<string, unknown> | undefined;
      if (cap && cap.changed && typeof cap.new_cap_cents === "number") {
        return `${stringOr(p.kind, "approval")} approved — weekly cap raised to $${(
          (cap.new_cap_cents as number) / 100
        ).toFixed(0)}`;
      }
      return `${stringOr(p.kind, "approval")} modified`;
    }
    case "spend_intent":
      return `Intent: $${((Number(p.amount_cents) || 0) / 100).toFixed(2)} to ${stringOr(
        p.merchant_hint,
        "?",
      )} · ${stringOr(p.purpose, "")}`.trim();
    case "spend_authorized":
      return `Spend authorized: $${((Number(p.amount_cents) || 0) / 100).toFixed(
        2,
      )} to ${stringOr(p.merchant_name, stringOr(p.merchant_category, "?"))}`;
    case "spend_declined":
      return `Declined: ${stringOr(p.reason, "spend policy")}`;
    case "revenue_received":
      return `Revenue: $${((Number(p.amount_cents) || 0) / 100).toFixed(2)}`;
    case "specialist_completed":
      return `${stringOr(p.name, "specialist")} → ${stringOr(p.status, "ok")}`;
    case "kill_switch_activated":
      return "Kill switch activated — all agents halted.";
    case "error":
      return stringOr(p.message, stringOr(p.detail, "error"));
    default:
      return JSON.stringify(p);
  }
}

function stringOr(v: unknown, fallback: string): string {
  return typeof v === "string" || typeof v === "number" ? String(v) : fallback;
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    gap: 10,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(107,107,107,0.1)",
  },
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    alignSelf: "flex-start",
    borderWidth: 1,
  },
  badgeText: {
    fontSize: 9,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  summary: { color: colors.ink, fontSize: 13, lineHeight: 18 },
  metaRow: { flexDirection: "row", gap: 10, marginTop: 2 },
  meta: { color: colors.iron, fontSize: 10, fontFamily: "Menlo" },
  muted: { color: colors.iron, fontSize: 13, lineHeight: 19 },
  errorText: { color: colors.danger, fontSize: 12, marginVertical: 8 },
  loadMore: { paddingVertical: 12, alignItems: "center" },
  loadMoreText: { color: colors.iron, fontSize: 13 },
  endMarker: {
    color: colors.iron,
    fontSize: 11,
    textAlign: "center",
    marginVertical: 12,
  },
});
