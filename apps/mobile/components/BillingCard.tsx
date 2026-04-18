import { useEffect, useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { getBilling, type BillingState } from "@/lib/api";
import { colors } from "@/lib/colors";

/**
 * Billing summary — current tier, business-cap usage, month-to-date agent
 * cost. Shown on the Safety/Settings surface so all account-level controls
 * live in one place.
 */
export function BillingCard() {
  const [state, setState] = useState<BillingState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBilling()
      .then(setState)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <Text style={styles.error}>{error}</Text>;
  if (!state) return <Text style={styles.muted}>Loading…</Text>;

  const unlimited = state.max_businesses === 0;
  const pct = unlimited ? 0 : Math.min((state.businesses_used / state.max_businesses) * 100, 100);
  const barColor = pct > 90 ? colors.danger : pct > 66 ? colors.warning : colors.accent;

  return (
    <View style={{ gap: 10 }}>
      <View style={styles.headline}>
        <Text style={styles.tier}>{state.display_name}</Text>
        <Text style={styles.mtd}>${(state.month_to_date_cost_cents / 100).toFixed(2)} MTD</Text>
      </View>

      <View style={styles.row}>
        <Text style={styles.rowKey}>Businesses</Text>
        <Text style={styles.rowVal}>
          {state.businesses_used} {unlimited ? "· unlimited" : `/ ${state.max_businesses}`}
        </Text>
      </View>
      {!unlimited ? (
        <View style={styles.barTrack}>
          <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: barColor }]} />
        </View>
      ) : null}

      <Pressable
        style={styles.upgrade}
        onPress={() => Linking.openURL("mailto:support@helm.app?subject=Upgrade%20request")}
      >
        <Text style={styles.upgradeText}>Contact to upgrade →</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  headline: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
  },
  tier: { fontSize: 22, fontWeight: "600", color: colors.ink },
  mtd: { fontSize: 12, color: colors.iron, fontFamily: "Menlo" },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
  },
  rowKey: { fontSize: 13, color: colors.iron },
  rowVal: { fontSize: 13, color: colors.ink, fontFamily: "Menlo" },
  barTrack: {
    height: 6,
    backgroundColor: "rgba(107,107,107,0.2)",
    borderRadius: 3,
    overflow: "hidden",
  },
  barFill: { height: "100%", borderRadius: 3 },
  upgrade: { alignSelf: "flex-start", paddingVertical: 6 },
  upgradeText: { color: colors.accent, fontSize: 13, fontWeight: "600" },
  error: { color: colors.danger, fontSize: 13 },
  muted: { color: colors.iron, fontSize: 13 },
});
