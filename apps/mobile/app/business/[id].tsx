import * as Haptics from "expo-haptics";
import * as Linking from "expo-linking";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { ActivityFeed } from "@/components/ActivityFeed";
import {
  connectToolkit,
  getBusiness,
  listIntegrations,
  startStripeOnboarding,
  syncIntegration,
  type BusinessDetail,
  type Integration,
} from "@/lib/api";
import { colors } from "@/lib/colors";

const TOOLKITS: { slug: string; label: string; hint: string }[] = [
  { slug: "gmail", label: "Gmail", hint: "Customer replies + transactional email" },
  { slug: "slack", label: "Slack", hint: "Ops + on-call notifications" },
  { slug: "reddit", label: "Reddit", hint: "Idea Scout — trend mining" },
  { slug: "hackernews", label: "Hacker News", hint: "Idea Scout — trend mining" },
  { slug: "product_hunt", label: "Product Hunt", hint: "Idea Scout — launch signal" },
  { slug: "shopify", label: "Shopify", hint: "Storefront + orders" },
];

export default function BusinessDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [integrations, setIntegrations] = useState<Integration[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [onboarding, setOnboarding] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [connectingSlug, setConnectingSlug] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const [b, ints] = await Promise.all([getBusiness(id), listIntegrations(id)]);
      setBiz(b);
      setIntegrations(ints);
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

  async function onConnectStripe() {
    if (!id) return;
    setOnboarding(true);
    setError(null);
    try {
      const resp = await startStripeOnboarding(id);
      Haptics.selectionAsync();
      await WebBrowser.openAuthSessionAsync(resp.onboarding_url, Linking.createURL("/"));
      await load();
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOnboarding(false);
    }
  }

  async function onConnectToolkit(slug: string) {
    if (!id) return;
    setConnectingSlug(slug);
    setError(null);
    try {
      const resp = await connectToolkit(id, slug);
      Haptics.selectionAsync();
      setPickerOpen(false);
      const result = await WebBrowser.openAuthSessionAsync(
        resp.redirect_url,
        Linking.createURL("/"),
      );
      // Regardless of how the session ended (success/cancel/dismiss), ask
      // the server to reconcile with Composio — a webhook might have already
      // flipped it to active, or the user might have completed auth.
      try {
        await syncIntegration(resp.integration_id);
      } catch {
        // Sync error surfaces via the refreshed list, not a blocking toast.
      }
      if (result.type === "success" || result.type === "dismiss") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      await load();
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConnectingSlug(null);
    }
  }

  async function onSyncIntegration(integrationId: string) {
    try {
      await syncIntegration(integrationId);
      Haptics.selectionAsync();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!biz) {
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

  const brandName = typeof biz.brand_kit?.name === "string" ? biz.brand_kit.name : null;
  const brandTagline = typeof biz.brand_kit?.tagline === "string" ? biz.brand_kit.tagline : null;

  return (
    <View style={styles.container}>
      <Stack.Screen options={{ title: biz.name }} />
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <View style={styles.header}>
          <Text style={styles.subtitle}>
            {biz.vertical} · {biz.status}
          </Text>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Card
          title="Money"
          description="Stripe Connect + Issuing per business. Weekly cap enforced."
        >
          <KV k="Weekly cap" v={`$${(biz.weekly_spend_cap_cents / 100).toFixed(0)}`} />
          <KV k="Stripe account" v={biz.stripe_account_id ?? "not connected"} />
          <KV k="Issuing card" v={biz.stripe_card_id ?? "not provisioned"} />
          <Pressable
            style={[styles.primary, onboarding && { opacity: 0.6 }]}
            onPress={onConnectStripe}
            disabled={onboarding}
          >
            {onboarding ? (
              <ActivityIndicator color={colors.paper} />
            ) : (
              <Text style={styles.primaryText}>
                {biz.stripe_account_id ? "Resume Stripe onboarding" : "Connect Stripe"}
              </Text>
            )}
          </Pressable>
        </Card>

        <Card
          title="Integrations"
          description="Composio-mediated OAuth. Specialists use these to act on the business's behalf."
        >
          {integrations === null ? (
            <ActivityIndicator style={{ marginVertical: 12 }} color={colors.iron} />
          ) : integrations.length === 0 ? (
            <Text style={styles.muted}>No integrations yet.</Text>
          ) : (
            <View style={{ gap: 8 }}>
              {integrations.map((i) => (
                <IntegrationRow key={i.id} row={i} onSync={() => onSyncIntegration(i.id)} />
              ))}
            </View>
          )}
          <Pressable style={styles.secondary} onPress={() => setPickerOpen(true)}>
            <Text style={styles.secondaryText}>+ Connect a toolkit</Text>
          </Pressable>
        </Card>

        <Card
          title="Activity"
          description="Every tool call, approval, and spend. Event-sourced — this is the record."
        >
          <ActivityFeed businessId={biz.id} />
        </Card>

        <Card
          title="Brand"
          description="What Creative Director set up. Ask the CEO to refine it from the chat."
        >
          {brandName ? (
            <View style={{ gap: 4 }}>
              <Text style={styles.brandName}>{brandName}</Text>
              {brandTagline ? <Text style={styles.muted}>{brandTagline}</Text> : null}
            </View>
          ) : (
            <Text style={styles.muted}>
              No brand kit yet. Open chat and ask the CEO to brief Creative Director.
            </Text>
          )}
        </Card>
      </ScrollView>

      <ToolkitPicker
        open={pickerOpen}
        connectedSlugs={new Set((integrations ?? []).map((i) => i.toolkit))}
        connecting={connectingSlug}
        onClose={() => setPickerOpen(false)}
        onPick={onConnectToolkit}
      />
    </View>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.kv}>
      <Text style={styles.kvKey}>{k}</Text>
      <Text style={styles.kvVal} numberOfLines={1}>
        {v}
      </Text>
    </View>
  );
}

function Card({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {description ? <Text style={styles.cardDesc}>{description}</Text> : null}
      <View style={{ marginTop: 10, gap: 8 }}>{children}</View>
    </View>
  );
}

function IntegrationRow({ row, onSync }: { row: Integration; onSync: () => void }) {
  const statusColor =
    row.status === "active"
      ? colors.success
      : row.status === "pending"
        ? colors.warning
        : colors.danger;
  return (
    <Pressable style={styles.intRow} onPress={onSync}>
      <View style={{ flex: 1 }}>
        <Text style={styles.intToolkit}>{row.toolkit}</Text>
        <Text style={[styles.intStatus, { color: statusColor }]}>{row.status}</Text>
      </View>
      <Text style={styles.intSync}>↻</Text>
    </Pressable>
  );
}

function ToolkitPicker({
  open,
  connectedSlugs,
  connecting,
  onClose,
  onPick,
}: {
  open: boolean;
  connectedSlugs: Set<string>;
  connecting: string | null;
  onClose: () => void;
  onPick: (slug: string) => void;
}) {
  return (
    <Modal visible={open} animationType="slide" onRequestClose={onClose} transparent>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalSheet}>
          <Text style={styles.modalTitle}>Connect a toolkit</Text>
          <Text style={styles.muted}>Composio handles OAuth. We never see the tokens.</Text>
          <View style={{ gap: 8, marginTop: 16 }}>
            {TOOLKITS.map((t) => {
              const connected = connectedSlugs.has(t.slug);
              const busy = connecting === t.slug;
              return (
                <Pressable
                  key={t.slug}
                  style={[styles.toolkitRow, connected && { opacity: 0.5 }]}
                  onPress={() => (connected || busy ? null : onPick(t.slug))}
                  disabled={connected || busy}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.toolkitLabel}>{t.label}</Text>
                    <Text style={styles.toolkitHint}>{t.hint}</Text>
                  </View>
                  {busy ? (
                    <ActivityIndicator color={colors.accent} />
                  ) : connected ? (
                    <Text style={[styles.toolkitMeta, { color: colors.success }]}>connected</Text>
                  ) : (
                    <Text style={styles.toolkitMeta}>connect →</Text>
                  )}
                </Pressable>
              );
            })}
          </View>
          <Pressable style={styles.cancel} onPress={onClose}>
            <Text style={styles.cancelText}>Close</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.paper },
  scroll: { padding: 16, gap: 12, paddingBottom: 40 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  header: { marginBottom: 4 },
  subtitle: { fontSize: 13, color: colors.iron },
  error: { color: colors.danger, fontSize: 13 },
  link: { color: colors.iron, fontSize: 14 },
  muted: { color: colors.iron, fontSize: 13, lineHeight: 19 },

  card: {
    backgroundColor: colors.haze,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.2)",
  },
  cardTitle: { fontSize: 15, fontWeight: "600", color: colors.ink },
  cardDesc: { fontSize: 12, color: colors.iron, marginTop: 4, lineHeight: 17 },

  kv: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  kvKey: { color: colors.iron, fontSize: 13 },
  kvVal: {
    color: colors.ink,
    fontSize: 13,
    fontFamily: "Menlo",
    maxWidth: "60%",
  },

  primary: {
    marginTop: 12,
    backgroundColor: colors.accent,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
  },
  primaryText: { color: colors.paper, fontSize: 14, fontWeight: "500" },

  secondary: {
    marginTop: 12,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
  },
  secondaryText: { color: colors.ink, fontSize: 14, fontWeight: "500" },

  intRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: colors.paper,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.15)",
  },
  intToolkit: { fontSize: 14, fontWeight: "500", color: colors.ink, textTransform: "capitalize" },
  intStatus: {
    fontSize: 11,
    fontFamily: "Menlo",
    marginTop: 2,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  intSync: { fontSize: 18, color: colors.iron, paddingHorizontal: 8 },

  brandName: { fontSize: 15, fontWeight: "500", color: colors.ink },

  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  modalSheet: {
    backgroundColor: colors.paper,
    padding: 20,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    maxHeight: "80%",
  },
  modalTitle: { fontSize: 18, fontWeight: "600", color: colors.ink, marginBottom: 6 },
  toolkitRow: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    backgroundColor: colors.haze,
    borderRadius: 8,
  },
  toolkitLabel: { color: colors.ink, fontSize: 15, fontWeight: "500" },
  toolkitHint: { color: colors.iron, fontSize: 12, marginTop: 2 },
  toolkitMeta: { color: colors.accent, fontSize: 12, fontWeight: "500" },
  cancel: { marginTop: 16, paddingVertical: 12, alignItems: "center" },
  cancelText: { color: colors.iron, fontSize: 15 },
});
