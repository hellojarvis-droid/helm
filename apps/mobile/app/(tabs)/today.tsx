import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  AppState,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { PausedBanner } from "@/components/PausedBanner";
import { getToday, type BusinessToday, type TodaySummary } from "@/lib/api";
import { colors } from "@/lib/colors";

export default function TodayScreen() {
  const router = useRouter();
  const [data, setData] = useState<TodaySummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getToday());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    // Auto-refresh every 60s in foreground + immediately on app foreground.
    // Catches push-driven approvals + spend events without manual pull.
    const interval = setInterval(load, 60_000);
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") void load();
    });
    return () => {
      clearInterval(interval);
      sub.remove();
    };
  }, [load]);

  async function onRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  return (
    <View style={styles.container}>
      <PausedBanner />
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {error ? <Text style={styles.error}>{error}</Text> : null}
        {data === null && !error ? (
          <ActivityIndicator style={{ marginTop: 60 }} color={colors.iron} />
        ) : null}
        {data && data.businesses.length === 0 ? (
          <View style={styles.heroBlock}>
            <Text style={styles.heroEyebrow}>Welcome to Helm</Text>
            <Text style={styles.heroTitle}>Tell your CEO Agent what to launch.</Text>
            <Text style={styles.heroBody}>
              Eight specialists are standing by. Idea Scout finds proven concepts. Creative Director
              builds the brand. Product Builder stands up the storefront. Ads Operator buys the
              first traffic.
            </Text>
            <Pressable
              style={styles.heroPrimary}
              onPress={() => router.push({ pathname: "/(tabs)/chat" })}
            >
              <Text style={styles.heroPrimaryText}>Open chat →</Text>
            </Pressable>
          </View>
        ) : null}

        {data && data.businesses.length > 0 ? (
          <>
            <View style={styles.headline}>
              <Text style={styles.label}>Net last 24h</Text>
              <Text
                style={[
                  styles.net,
                  { color: data.net_today_cents >= 0 ? colors.success : colors.danger },
                ]}
              >
                {data.net_today_cents >= 0 ? "+" : "−"}$
                {(Math.abs(data.net_today_cents) / 100).toFixed(2)}
              </Text>
              <View style={styles.subRow}>
                <Text style={styles.sub}>
                  +${(data.revenue_today_cents / 100).toFixed(2)} revenue
                </Text>
                <Text style={styles.sub}>−${(data.spend_today_cents / 100).toFixed(2)} spend</Text>
              </View>
            </View>

            {data.pending_approval_count > 0 ? (
              <Pressable
                style={styles.pendingBanner}
                onPress={() => router.push({ pathname: "/(tabs)/approvals" })}
              >
                <Text style={styles.pendingText}>
                  {data.pending_approval_count} approval
                  {data.pending_approval_count === 1 ? "" : "s"} waiting on you →
                </Text>
              </Pressable>
            ) : null}

            <Text style={styles.sectionTitle}>Businesses</Text>
            <View style={{ gap: 8 }}>
              {data.businesses.map((b) => (
                <BusinessRow
                  key={b.id}
                  biz={b}
                  onPress={() => router.push({ pathname: "/business/[id]", params: { id: b.id } })}
                />
              ))}
            </View>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

function BusinessRow({ biz, onPress }: { biz: BusinessToday; onPress: () => void }) {
  const netPositive = biz.net_today_cents >= 0;
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <View style={{ flex: 1 }}>
        <Text style={styles.rowName}>{biz.name}</Text>
        <Text style={styles.rowVertical}>
          {biz.vertical} · {biz.status}
        </Text>
      </View>
      <View style={styles.rowMeta}>
        <Text style={[styles.rowNet, { color: netPositive ? colors.success : colors.danger }]}>
          {netPositive ? "+" : "−"}${(Math.abs(biz.net_today_cents) / 100).toFixed(0)}
        </Text>
        {biz.pending_approval_count > 0 ? (
          <Text style={styles.rowPending}>● {biz.pending_approval_count} approval</Text>
        ) : (
          <Text style={styles.rowSub}>
            ${(biz.revenue_today_cents / 100).toFixed(0)}r · $
            {(biz.spend_today_cents / 100).toFixed(0)}s
          </Text>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.paper },
  scroll: { padding: 16, gap: 16, paddingBottom: 40 },
  error: { color: colors.danger, fontSize: 13 },
  muted: { color: colors.iron, fontSize: 13, lineHeight: 19 },

  heroBlock: { paddingTop: 32, paddingBottom: 24, gap: 12, alignItems: "center" },
  heroEyebrow: {
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 2,
    color: colors.accent,
    textTransform: "uppercase",
  },
  heroTitle: {
    fontSize: 26,
    fontWeight: "600",
    color: colors.ink,
    textAlign: "center",
    paddingHorizontal: 8,
    lineHeight: 32,
  },
  heroBody: {
    fontSize: 14,
    color: colors.iron,
    textAlign: "center",
    lineHeight: 20,
    paddingHorizontal: 16,
  },
  heroPrimary: {
    marginTop: 8,
    backgroundColor: colors.accent,
    paddingHorizontal: 22,
    paddingVertical: 12,
    borderRadius: 8,
  },
  heroPrimaryText: { color: colors.paper, fontWeight: "600", fontSize: 15 },
  headline: { gap: 2 },
  label: {
    color: colors.iron,
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1,
    fontWeight: "600",
  },
  net: { fontSize: 44, fontWeight: "600", fontFamily: "Menlo", marginTop: 4 },
  subRow: { flexDirection: "row", gap: 16, marginTop: 4 },
  sub: { color: colors.iron, fontSize: 13, fontFamily: "Menlo" },

  pendingBanner: {
    backgroundColor: colors.accent,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 8,
  },
  pendingText: { color: colors.paper, fontSize: 14, fontWeight: "600" },

  sectionTitle: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1,
    fontWeight: "600",
    color: colors.ink,
    marginTop: 8,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.haze,
    padding: 14,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.15)",
  },
  rowName: { fontSize: 15, fontWeight: "500", color: colors.ink },
  rowVertical: { fontSize: 12, color: colors.iron, marginTop: 2 },
  rowMeta: { alignItems: "flex-end" },
  rowNet: { fontSize: 18, fontWeight: "600", fontFamily: "Menlo" },
  rowSub: { fontSize: 11, color: colors.iron, fontFamily: "Menlo", marginTop: 2 },
  rowPending: { fontSize: 11, color: colors.accent, marginTop: 2, fontWeight: "600" },
});
