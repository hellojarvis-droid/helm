import * as Haptics from "expo-haptics";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { getApproval, respondToApproval, type Approval } from "@/lib/api";
import { colors } from "@/lib/colors";

const STATUS_TINT: Record<string, string> = {
  pending: colors.warning,
  approved: colors.success,
  modified: colors.accent,
  denied: colors.danger,
  expired: colors.iron,
};

export default function ApprovalDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [approval, setApproval] = useState<Approval | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      setApproval(await getApproval(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  async function respond(
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) {
    if (!id) return;
    setBusy(true);
    setError(null);
    Haptics.impactAsync(
      status === "denied" ? Haptics.ImpactFeedbackStyle.Light : Haptics.ImpactFeedbackStyle.Medium,
    );
    try {
      const updated = await respondToApproval(id, status, modifications);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setApproval(updated);
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!approval) {
    return (
      <View style={styles.container}>
        <Stack.Screen options={{ title: "" }} />
        {error ? (
          <View style={styles.center}>
            <Text style={styles.error}>{error}</Text>
            <Pressable onPress={() => router.back()} style={{ marginTop: 16 }}>
              <Text style={styles.link}>← Back</Text>
            </Pressable>
          </View>
        ) : (
          <ActivityIndicator style={{ marginTop: 60 }} color={colors.iron} />
        )}
      </View>
    );
  }

  const isSpend =
    approval.kind === "spend" &&
    typeof approval.details?.amount_cents === "number" &&
    (approval.details.amount_cents as number) > 0;
  const amountCents = isSpend ? (approval.details.amount_cents as number) : 0;
  const merchant =
    typeof approval.details?.merchant_hint === "string"
      ? (approval.details.merchant_hint as string)
      : "";
  const purpose =
    typeof approval.details?.purpose === "string" ? (approval.details.purpose as string) : "";
  const tint = STATUS_TINT[approval.status] ?? colors.iron;

  return (
    <View style={styles.container}>
      <Stack.Screen options={{ title: isSpend ? "Spend approval" : "Approval" }} />
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <View style={styles.header}>
          <Text style={[styles.eyebrow, { color: tint }]}>
            {isSpend ? "Spend approval" : approval.kind} · {approval.status}
          </Text>
          {isSpend ? (
            <View style={styles.amountRow}>
              <Text style={styles.amount}>${(amountCents / 100).toFixed(2)}</Text>
              {merchant ? <Text style={styles.merchant}>to {merchant}</Text> : null}
            </View>
          ) : (
            <Text style={styles.title}>{approval.summary}</Text>
          )}
        </View>

        {isSpend && purpose ? (
          <Card title="Why">
            <Text style={styles.body}>{purpose}</Text>
          </Card>
        ) : null}

        <Card title="Summary">
          <Text style={styles.body}>{approval.summary}</Text>
        </Card>

        <Card title="Timing">
          <KV k="Requested" v={new Date(approval.requested_at).toLocaleString()} />
          <KV k="Expires" v={new Date(approval.expires_at).toLocaleString()} />
          {approval.responded_at ? (
            <KV k="Responded" v={new Date(approval.responded_at).toLocaleString()} />
          ) : null}
        </Card>

        <Card title="Details">
          <Text style={styles.code}>{JSON.stringify(approval.details, null, 2)}</Text>
        </Card>

        {approval.status === "pending" ? (
          <View style={styles.actions}>
            <Pressable
              style={[styles.approve, busy && { opacity: 0.6 }]}
              disabled={busy}
              onPress={() => respond("approved")}
            >
              <Text style={styles.approveText}>
                {isSpend ? `Approve $${(amountCents / 100).toFixed(0)}` : "Approve"}
              </Text>
            </Pressable>
            {isSpend ? (
              <Pressable
                style={[styles.raiseCap, busy && { opacity: 0.6 }]}
                disabled={busy}
                onPress={() => respond("modified", { raise_weekly_cap: true })}
              >
                <Text style={styles.raiseCapText}>Approve & raise cap</Text>
              </Pressable>
            ) : null}
            <Pressable
              style={[styles.deny, busy && { opacity: 0.6 }]}
              disabled={busy}
              onPress={() => respond("denied")}
            >
              <Text style={styles.denyText}>Deny</Text>
            </Pressable>
          </View>
        ) : null}

        {error ? <Text style={styles.error}>{error}</Text> : null}
      </ScrollView>
    </View>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      <View style={{ marginTop: 8, gap: 6 }}>{children}</View>
    </View>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.kv}>
      <Text style={styles.kvKey}>{k}</Text>
      <Text style={styles.kvVal}>{v}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.paper },
  scroll: { padding: 16, gap: 12, paddingBottom: 40 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  header: { gap: 6, marginBottom: 4 },
  eyebrow: { fontSize: 11, fontWeight: "600", textTransform: "uppercase", letterSpacing: 1 },
  title: { fontSize: 20, color: colors.ink, fontWeight: "600" },
  amountRow: { flexDirection: "row", alignItems: "baseline", gap: 8 },
  amount: { fontSize: 32, fontWeight: "600", color: colors.ink, fontFamily: "Menlo" },
  merchant: { fontSize: 13, color: colors.iron },
  card: {
    backgroundColor: colors.haze,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.2)",
  },
  cardTitle: {
    fontSize: 11,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 1,
    color: colors.ink,
  },
  body: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  code: {
    color: colors.ink,
    fontSize: 11,
    fontFamily: "Menlo",
    lineHeight: 15,
  },
  kv: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  kvKey: { color: colors.iron, fontSize: 13 },
  kvVal: { color: colors.ink, fontSize: 13, fontFamily: "Menlo" },
  actions: { gap: 8, marginTop: 4 },
  approve: {
    backgroundColor: colors.accent,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
  },
  approveText: { color: colors.paper, fontSize: 14, fontWeight: "600" },
  raiseCap: {
    borderWidth: 1,
    borderColor: colors.accent,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
  },
  raiseCapText: { color: colors.accent, fontSize: 14, fontWeight: "500" },
  deny: {
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
  },
  denyText: { color: colors.iron, fontSize: 14, fontWeight: "500" },
  error: { color: colors.danger, fontSize: 13 },
  link: { color: colors.iron, fontSize: 14 },
});
