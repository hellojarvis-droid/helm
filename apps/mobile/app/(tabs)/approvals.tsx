import * as Haptics from "expo-haptics";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { PausedBanner } from "@/components/PausedBanner";
import { listApprovals, respondToApproval, type Approval } from "@/lib/api";
import { colors } from "@/lib/colors";

const TABS = ["pending", "approved", "denied"] as const;
type Tab = (typeof TABS)[number];

export default function ApprovalsScreen() {
  const [tab, setTab] = useState<Tab>("pending");
  const [rows, setRows] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setRows(await listApprovals(tab));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [tab]);

  useEffect(() => {
    setRows(null);
    void load();
  }, [load]);

  async function onRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  async function respond(id: string, status: "approved" | "denied") {
    Haptics.impactAsync(
      status === "approved"
        ? Haptics.ImpactFeedbackStyle.Medium
        : Haptics.ImpactFeedbackStyle.Light,
    );
    try {
      await respondToApproval(id, status);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      await load();
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <View style={styles.container}>
      <PausedBanner />
      <View style={styles.tabs}>
        {TABS.map((t) => (
          <Pressable
            key={t}
            style={[styles.tab, tab === t && styles.tabActive]}
            onPress={() => setTab(t)}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>{t}</Text>
          </Pressable>
        ))}
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <FlatList
        data={rows ?? []}
        keyExtractor={(a) => a.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        renderItem={({ item }) => <Card approval={item} onRespond={respond} />}
        ListEmptyComponent={
          rows === null ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={colors.iron} />
          ) : (
            <Text style={styles.empty}>Nothing {tab}.</Text>
          )
        }
      />
    </View>
  );
}

function Card({
  approval,
  onRespond,
}: {
  approval: Approval;
  onRespond: (id: string, status: "approved" | "denied") => void;
}) {
  const pending = approval.status === "pending";
  return (
    <View style={[styles.card, pending && styles.cardPending]}>
      <Text style={styles.kind}>
        {approval.kind} · <Text style={{ color: colors.iron }}>{approval.status}</Text>
      </Text>
      <Text style={styles.summary}>{approval.summary}</Text>
      {pending ? (
        <View style={styles.actions}>
          <Pressable style={styles.approve} onPress={() => onRespond(approval.id, "approved")}>
            <Text style={styles.approveText}>Approve</Text>
          </Pressable>
          <Pressable style={styles.deny} onPress={() => onRespond(approval.id, "denied")}>
            <Text style={styles.denyText}>Deny</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.paper },
  tabs: {
    flexDirection: "row",
    borderBottomColor: "rgba(107,107,107,0.2)",
    borderBottomWidth: 1,
    paddingHorizontal: 4,
  },
  tab: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 2,
    borderBottomColor: "transparent",
  },
  tabActive: { borderBottomColor: colors.accent },
  tabText: { color: colors.iron, fontSize: 13, textTransform: "capitalize" },
  tabTextActive: { color: colors.ink, fontWeight: "500" },
  list: { padding: 16, gap: 10 },
  empty: { textAlign: "center", color: colors.iron, marginTop: 40 },
  error: { color: colors.danger, padding: 16 },
  card: {
    backgroundColor: colors.haze,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.2)",
  },
  cardPending: {
    borderColor: "rgba(232,93,26,0.4)",
    backgroundColor: "rgba(232,93,26,0.06)",
  },
  kind: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1,
    fontWeight: "600",
    color: colors.ink,
    marginBottom: 8,
  },
  summary: { fontSize: 14, color: colors.ink, lineHeight: 20, marginBottom: 12 },
  actions: { flexDirection: "row", gap: 8 },
  approve: {
    backgroundColor: colors.accent,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
  },
  approveText: { color: colors.paper, fontWeight: "500" },
  deny: {
    backgroundColor: "transparent",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
  },
  denyText: { color: colors.iron, fontWeight: "500" },
});
