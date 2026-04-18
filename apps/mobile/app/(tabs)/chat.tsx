import * as Haptics from "expo-haptics";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { PausedBanner } from "@/components/PausedBanner";
import { respondToApproval, streamChatTurn, type ChatEvent } from "@/lib/api";
import { colors } from "@/lib/colors";

type ApprovalPart = {
  kind: "approval";
  approval_id: string;
  approval_kind: string;
  summary: string;
  details?: Record<string, unknown>;
  business_id: string;
  expires_at: string;
  resolvedAs?: "approved" | "denied" | "approved+cap_raised";
};

type TurnPart =
  | { kind: "user"; text: string }
  | { kind: "agent"; text: string; toolCalls: string[]; costCents: number }
  | { kind: "tool"; name: string; ok: boolean }
  | ApprovalPart
  | { kind: "error"; text: string };

export default function ChatScreen() {
  const [parts, setParts] = useState<TurnPart[]>([]);
  const [pending, setPending] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<FlatList<TurnPart>>(null);

  useEffect(() => {
    // Auto-scroll on every append so the newest part is always visible.
    const t = setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 20);
    return () => clearTimeout(t);
  }, [parts.length, pending]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setPending("");
    setParts((p) => [...p, { kind: "user", text }]);
    Haptics.selectionAsync();

    let acc = "";
    let toolCalls: string[] = [];
    let costCents = 0;

    try {
      for await (const ev of streamChatTurn(text)) {
        if (ev.kind === "text_delta") {
          acc += ev.text;
          setPending(acc);
        } else if (ev.kind === "tool_call") {
          toolCalls = [...toolCalls, ev.name];
          setParts((p) => [...p, { kind: "tool", name: ev.name, ok: true }]);
        } else if (ev.kind === "tool_result") {
          setParts((p) => [...p, { kind: "tool", name: ev.name, ok: !ev.is_error }]);
        } else if (ev.kind === "approval_requested") {
          // Subtle notification haptic when an approval arrives.
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
          setParts((p) => [
            ...p,
            {
              kind: "approval",
              approval_id: ev.approval_id,
              approval_kind: ev.approval_kind,
              summary: ev.summary,
              details: ev.details,
              business_id: ev.business_id,
              expires_at: ev.expires_at,
            },
          ]);
        } else if (ev.kind === "turn_cost") {
          costCents = ev.cost_cents;
        } else if (ev.kind === "done") {
          if (acc) {
            setParts((p) => [...p, { kind: "agent", text: acc, toolCalls, costCents }]);
          }
          setPending("");
        } else if (ev.kind === "error") {
          setParts((p) => [
            ...p,
            {
              kind: "error",
              text: `${ev.reason}${ev.detail ? `: ${ev.detail}` : ""}`,
            },
          ]);
        }
      }
    } catch (e) {
      setParts((p) => [...p, { kind: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setBusy(false);
    }
  }

  async function respond(
    approvalId: string,
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) {
    Haptics.impactAsync(
      status === "denied" ? Haptics.ImpactFeedbackStyle.Light : Haptics.ImpactFeedbackStyle.Medium,
    );
    try {
      await respondToApproval(approvalId, status, modifications);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      const resolvedAs: ApprovalPart["resolvedAs"] =
        status === "modified" && modifications?.raise_weekly_cap
          ? "approved+cap_raised"
          : status === "modified"
            ? "approved"
            : status;
      setParts((prev) =>
        prev.map((p) =>
          p.kind === "approval" && p.approval_id === approvalId ? { ...p, resolvedAs } : p,
        ),
      );
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setParts((prev) => [
        ...prev,
        { kind: "error", text: e instanceof Error ? e.message : String(e) },
      ]);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <PausedBanner />
      <FlatList
        ref={listRef}
        data={parts}
        keyExtractor={(_, i) => String(i)}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => <PartView part={item} onRespond={respond} />}
        ListEmptyComponent={
          !pending ? (
            <Text style={styles.empty}>Start a conversation. The CEO Agent is listening.</Text>
          ) : null
        }
        ListFooterComponent={pending ? <PendingText text={pending} /> : null}
      />

      <View style={styles.composer}>
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder={busy ? "working…" : "Tell the CEO Agent what to do"}
          placeholderTextColor={colors.iron}
          style={styles.input}
          editable={!busy}
          onSubmitEditing={send}
          returnKeyType="send"
          multiline
        />
        <Pressable
          style={[styles.send, (!input.trim() || busy) && styles.sendDisabled]}
          onPress={send}
          disabled={busy || !input.trim()}
        >
          {busy ? (
            <ActivityIndicator color={colors.paper} />
          ) : (
            <Text style={styles.sendText}>Send</Text>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

function PartView({
  part,
  onRespond,
}: {
  part: TurnPart;
  onRespond: (
    id: string,
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) => void;
}) {
  if (part.kind === "user") {
    return (
      <View style={styles.userRow}>
        <View style={styles.userBubble}>
          <Text style={styles.userText}>{part.text}</Text>
        </View>
      </View>
    );
  }
  if (part.kind === "agent") {
    return (
      <View style={{ marginBottom: 12 }}>
        <Text style={styles.agentText}>{part.text}</Text>
        {part.toolCalls.length ? (
          <Text style={styles.meta}>tools: {part.toolCalls.join(", ")}</Text>
        ) : null}
        {part.costCents > 0 ? <Text style={styles.meta}>cost: {part.costCents}¢</Text> : null}
      </View>
    );
  }
  if (part.kind === "tool") {
    return (
      <Text style={[styles.toolLine, !part.ok && { color: colors.danger }]}>
        {part.ok ? "✓" : "✗"} {part.name}
      </Text>
    );
  }
  if (part.kind === "error") {
    return <Text style={styles.errorText}>! {part.text}</Text>;
  }
  return <ApprovalCardInline part={part} onRespond={onRespond} />;
}

function ApprovalCardInline({
  part,
  onRespond,
}: {
  part: ApprovalPart;
  onRespond: (
    id: string,
    status: "approved" | "denied" | "modified",
    modifications?: Record<string, unknown>,
  ) => void;
}) {
  const expires = new Date(part.expires_at).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });

  if (part.resolvedAs) {
    const label =
      part.resolvedAs === "approved+cap_raised"
        ? "approval approved + cap raised"
        : `approval ${part.resolvedAs}`;
    return <Text style={[styles.toolLine, { color: colors.accent }]}>✓ {label}</Text>;
  }

  const d = part.details ?? {};
  const isSpend =
    part.approval_kind === "spend" &&
    typeof d.amount_cents === "number" &&
    (d.amount_cents as number) > 0;

  if (isSpend) {
    const amountCents = d.amount_cents as number;
    const merchant = typeof d.merchant_hint === "string" ? (d.merchant_hint as string) : "";
    const purpose = typeof d.purpose === "string" ? (d.purpose as string) : "";
    return (
      <View style={[styles.approvalCard, styles.spendApprovalCard]}>
        <View style={styles.approvalHeader}>
          <Text style={styles.approvalKind}>Spend approval</Text>
          <Text style={styles.approvalExpiry}>expires {expires}</Text>
        </View>
        <View style={styles.spendAmountRow}>
          <Text style={styles.spendAmount}>${(amountCents / 100).toFixed(2)}</Text>
          {merchant ? <Text style={styles.spendMerchant}>to {merchant}</Text> : null}
        </View>
        {purpose ? (
          <Text style={styles.spendPurpose}>
            <Text style={{ color: colors.iron }}>Why: </Text>
            {purpose}
          </Text>
        ) : null}
        <Text style={styles.spendSummary}>{part.summary}</Text>
        <View style={[styles.approvalActions, { flexWrap: "wrap" }]}>
          <Pressable
            style={styles.approveBtn}
            onPress={() => onRespond(part.approval_id, "approved")}
          >
            <Text style={styles.approveText}>Approve ${(amountCents / 100).toFixed(0)}</Text>
          </Pressable>
          <Pressable
            style={styles.raiseCapBtn}
            onPress={() => onRespond(part.approval_id, "modified", { raise_weekly_cap: true })}
          >
            <Text style={styles.raiseCapText}>Approve & raise cap</Text>
          </Pressable>
          <Pressable style={styles.denyBtn} onPress={() => onRespond(part.approval_id, "denied")}>
            <Text style={styles.denyText}>Deny</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.approvalCard}>
      <View style={styles.approvalHeader}>
        <Text style={styles.approvalKind}>Approval · {part.approval_kind}</Text>
        <Text style={styles.approvalExpiry}>expires {expires}</Text>
      </View>
      <Text style={styles.approvalSummary}>{part.summary}</Text>
      <View style={styles.approvalActions}>
        <Pressable
          style={styles.approveBtn}
          onPress={() => onRespond(part.approval_id, "approved")}
        >
          <Text style={styles.approveText}>Approve</Text>
        </Pressable>
        <Pressable style={styles.denyBtn} onPress={() => onRespond(part.approval_id, "denied")}>
          <Text style={styles.denyText}>Deny</Text>
        </Pressable>
      </View>
    </View>
  );
}

function PendingText({ text }: { text: string }) {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.2, duration: 450, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1.0, duration: 450, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={styles.agentText}>
        {text}
        <Animated.Text style={[styles.caret, { opacity }]}>▌</Animated.Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.paper },
  list: { padding: 16, gap: 8 },
  empty: { textAlign: "center", marginTop: 80, color: colors.iron, fontSize: 14 },
  userRow: { alignItems: "flex-end", marginBottom: 8 },
  userBubble: {
    backgroundColor: colors.ink,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
    maxWidth: "85%",
  },
  userText: { color: colors.paper, fontSize: 15 },
  agentText: { color: colors.ink, fontSize: 15, lineHeight: 22 },
  caret: { color: colors.ink, fontSize: 16 },
  errorText: { color: colors.danger, fontSize: 13, marginBottom: 8 },
  toolLine: {
    color: colors.iron,
    fontSize: 11,
    fontFamily: Platform.select({ ios: "Menlo", android: "monospace" }),
    marginTop: 2,
    marginBottom: 2,
  },
  meta: {
    color: colors.iron,
    fontSize: 11,
    fontFamily: Platform.select({ ios: "Menlo", android: "monospace" }),
    marginTop: 4,
  },
  composer: {
    flexDirection: "row",
    gap: 8,
    padding: 12,
    borderTopColor: "rgba(107,107,107,0.2)",
    borderTopWidth: 1,
    backgroundColor: colors.paper,
  },
  input: {
    flex: 1,
    backgroundColor: colors.haze,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
    fontSize: 15,
    color: colors.ink,
    maxHeight: 120,
  },
  send: {
    backgroundColor: colors.ink,
    paddingHorizontal: 16,
    borderRadius: 8,
    justifyContent: "center",
    alignItems: "center",
    minWidth: 72,
  },
  sendDisabled: { backgroundColor: colors.iron, opacity: 0.6 },
  sendText: { color: colors.paper, fontSize: 15, fontWeight: "500" },
  approvalCard: {
    borderColor: "rgba(232,93,26,0.4)",
    borderWidth: 1,
    backgroundColor: "rgba(232,93,26,0.06)",
    padding: 14,
    borderRadius: 12,
    marginVertical: 8,
  },
  spendApprovalCard: {
    borderColor: colors.accent,
    borderWidth: 2,
  },
  spendAmountRow: {
    flexDirection: "row",
    alignItems: "baseline",
    gap: 8,
    marginBottom: 8,
  },
  spendAmount: {
    fontSize: 32,
    fontWeight: "600",
    color: colors.ink,
    fontFamily: "Menlo",
  },
  spendMerchant: { fontSize: 13, color: colors.iron },
  spendPurpose: { color: colors.ink, fontSize: 13, lineHeight: 18, marginBottom: 6 },
  spendSummary: {
    color: colors.iron,
    fontSize: 11,
    lineHeight: 16,
    marginBottom: 12,
  },
  approvalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginBottom: 8,
  },
  approvalKind: {
    color: colors.accent,
    fontSize: 11,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  approvalExpiry: { color: colors.iron, fontSize: 11 },
  approvalSummary: { color: colors.ink, fontSize: 14, lineHeight: 20, marginBottom: 12 },
  approvalActions: { flexDirection: "row", gap: 8 },
  approveBtn: {
    backgroundColor: colors.accent,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
  },
  approveText: { color: colors.paper, fontWeight: "500", fontSize: 14 },
  raiseCapBtn: {
    borderWidth: 1,
    borderColor: colors.accent,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
  },
  raiseCapText: { color: colors.accent, fontWeight: "500", fontSize: 14 },
  denyBtn: {
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
  },
  denyText: { color: colors.iron, fontWeight: "500", fontSize: 14 },
});
