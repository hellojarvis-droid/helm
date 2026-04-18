import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { getSpend, type SpendSummary } from "@/lib/api";
import { colors } from "@/lib/colors";

export function SpendCard({ businessId }: { businessId: string }) {
  const [s, setS] = useState<SpendSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSpend(businessId)
      .then(setS)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [businessId]);

  if (error) return <Text style={styles.error}>{error}</Text>;
  if (!s) return <Text style={styles.muted}>Loading…</Text>;

  const pct = s.weekly_cap_cents === 0 ? 0 : (s.week_to_date_cents / s.weekly_cap_cents) * 100;
  const barColor = pct > 90 ? colors.danger : pct > 66 ? colors.warning : colors.accent;

  return (
    <View style={{ gap: 10 }}>
      <View style={styles.headline}>
        <View>
          <Text style={styles.big}>{dollars(s.week_to_date_cents)}</Text>
          <Text style={styles.muted}>of {dollars(s.weekly_cap_cents)} cap</Text>
        </View>
        <Text style={styles.remaining}>{dollars(s.remaining_cents)} left</Text>
      </View>

      <View style={styles.barTrack}>
        <View
          style={[styles.barFill, { width: `${Math.min(pct, 100)}%`, backgroundColor: barColor }]}
        />
      </View>

      <View style={styles.metaRow}>
        <Meta k={`Revenue ${s.window_days}d`} v={dollars(s.revenue_wtd_cents)} success />
        <Meta
          k="Net"
          v={`${s.net_wtd_cents >= 0 ? "+" : "−"}${dollars(Math.abs(s.net_wtd_cents))}`}
          success={s.net_wtd_cents >= 0}
          danger={s.net_wtd_cents < 0}
        />
      </View>
      <View style={styles.metaRow}>
        <Meta k="LLM cost" v={cents(s.llm_cost_cents)} />
        {s.declined_count > 0 ? <Meta k="Declined" v={String(s.declined_count)} danger /> : null}
      </View>
    </View>
  );
}

function Meta({
  k,
  v,
  danger,
  success,
}: {
  k: string;
  v: string;
  danger?: boolean;
  success?: boolean;
}) {
  return (
    <View>
      <Text style={styles.metaKey}>{k}</Text>
      <Text
        style={[
          styles.metaVal,
          danger && { color: colors.danger },
          success && { color: colors.success },
        ]}
      >
        {v}
      </Text>
    </View>
  );
}

function dollars(c: number): string {
  return `$${(c / 100).toFixed(2)}`;
}

function cents(n: number): string {
  if (n === 0) return "0¢";
  if (n < 100) return `${n}¢`;
  return dollars(n);
}

const styles = StyleSheet.create({
  headline: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  big: { fontSize: 24, fontWeight: "600", color: colors.ink, fontFamily: "Menlo" },
  muted: { fontSize: 12, color: colors.iron },
  remaining: { fontSize: 13, color: colors.iron },
  barTrack: {
    height: 6,
    backgroundColor: "rgba(107,107,107,0.2)",
    borderRadius: 3,
    overflow: "hidden",
  },
  barFill: { height: "100%", borderRadius: 3 },
  metaRow: { flexDirection: "row", gap: 20, marginTop: 4 },
  metaKey: { fontSize: 10, color: colors.iron, textTransform: "uppercase", letterSpacing: 1 },
  metaVal: { fontSize: 12, color: colors.ink, fontFamily: "Menlo", marginTop: 2 },
  error: { color: colors.danger, fontSize: 13 },
});
