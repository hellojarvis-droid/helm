import * as Haptics from "expo-haptics";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { getBilling, openBillingPortal, startBillingCheckout, type BillingState } from "@/lib/api";
import { colors } from "@/lib/colors";

/**
 * Billing summary — current tier, business-cap usage, month-to-date agent
 * cost. Shown on the Safety/Settings surface so all account-level controls
 * live in one place.
 *
 * Active subscribers see "Manage subscription" which opens the Stripe
 * Customer Portal in an in-app browser. Non-subscribers see two upgrade
 * buttons that route through Stripe Checkout (also in-app browser).
 */
export function BillingCard() {
  const [state, setState] = useState<BillingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setState(await getBilling());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function openPortal() {
    setBusyAction("portal");
    setError(null);
    Haptics.selectionAsync();
    try {
      const { url } = await openBillingPortal();
      await WebBrowser.openAuthSessionAsync(url, Linking.createURL("/"));
      await refresh(); // pick up plan changes
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyAction(null);
    }
  }

  async function checkoutTier(target: "operator" | "portfolio") {
    setBusyAction(target);
    setError(null);
    Haptics.selectionAsync();
    try {
      const { url } = await startBillingCheckout(target);
      await WebBrowser.openAuthSessionAsync(url, Linking.createURL("/"));
      await refresh();
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyAction(null);
    }
  }

  if (error) return <Text style={styles.error}>{error}</Text>;
  if (!state) return <Text style={styles.muted}>Loading…</Text>;

  const unlimited = state.max_businesses === 0;
  const pct = unlimited ? 0 : Math.min((state.businesses_used / state.max_businesses) * 100, 100);
  const barColor = pct > 90 ? colors.danger : pct > 66 ? colors.warning : colors.accent;
  const isActive = state.subscription_status === "active";

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

      {state.subscription_status && state.subscription_status !== "inactive" ? (
        <Text style={styles.statusLine}>Status: {state.subscription_status}</Text>
      ) : null}

      <View style={styles.actions}>
        {isActive ? (
          <Pressable
            style={[styles.primary, busyAction !== null && { opacity: 0.5 }]}
            onPress={openPortal}
            disabled={busyAction !== null}
          >
            {busyAction === "portal" ? (
              <ActivityIndicator color={colors.paper} size="small" />
            ) : (
              <Text style={styles.primaryText}>Manage subscription</Text>
            )}
          </Pressable>
        ) : null}
        {state.tier !== "operator" ? (
          <Pressable
            style={[styles.secondary, busyAction !== null && { opacity: 0.5 }]}
            onPress={() => checkoutTier("operator")}
            disabled={busyAction !== null}
          >
            {busyAction === "operator" ? (
              <ActivityIndicator color={colors.accent} size="small" />
            ) : (
              <Text style={styles.secondaryText}>Upgrade to Operator</Text>
            )}
          </Pressable>
        ) : null}
        {state.tier !== "portfolio" ? (
          <Pressable
            style={[styles.secondary, busyAction !== null && { opacity: 0.5 }]}
            onPress={() => checkoutTier("portfolio")}
            disabled={busyAction !== null}
          >
            {busyAction === "portfolio" ? (
              <ActivityIndicator color={colors.accent} size="small" />
            ) : (
              <Text style={styles.secondaryText}>Upgrade to Portfolio</Text>
            )}
          </Pressable>
        ) : null}
      </View>
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
  statusLine: { fontSize: 11, color: colors.iron, fontFamily: "Menlo" },
  actions: { gap: 6, marginTop: 6 },
  primary: {
    backgroundColor: colors.ink,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: "center",
  },
  primaryText: { color: colors.paper, fontSize: 14, fontWeight: "500" },
  secondary: {
    borderWidth: 1,
    borderColor: colors.accent,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: "center",
  },
  secondaryText: { color: colors.accent, fontSize: 14, fontWeight: "500" },
  error: { color: colors.danger, fontSize: 13 },
  muted: { color: colors.iron, fontSize: 13 },
});
