import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { sendChatTurn, type ChatTurnResult } from "@/lib/api";
import { colors } from "@/lib/colors";

type Turn =
  | { role: "user"; text: string }
  | { role: "agent"; text: string; toolCalls: string[]; costCents: number }
  | { role: "error"; text: string };

export default function ChatScreen() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setTurns((prev) => [...prev, { role: "user", text }]);

    try {
      const result: ChatTurnResult = await sendChatTurn(text);
      if (result.error) {
        setTurns((prev) => [...prev, { role: "error", text: result.error ?? "unknown error" }]);
      } else {
        setTurns((prev) => [
          ...prev,
          {
            role: "agent",
            text: result.agentText,
            toolCalls: result.toolCalls,
            costCents: result.costCents,
          },
        ]);
      }
    } catch (e) {
      setTurns((prev) => [
        ...prev,
        { role: "error", text: e instanceof Error ? e.message : String(e) },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <FlatList
        data={turns}
        keyExtractor={(_, i) => String(i)}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => <Bubble turn={item} />}
        ListEmptyComponent={
          <Text style={styles.empty}>Start a conversation. The CEO Agent is listening.</Text>
        }
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

function Bubble({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <View style={styles.userRow}>
        <View style={styles.userBubble}>
          <Text style={styles.userText}>{turn.text}</Text>
        </View>
      </View>
    );
  }
  if (turn.role === "error") {
    return <Text style={styles.errorText}>! {turn.text}</Text>;
  }
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={styles.agentText}>{turn.text}</Text>
      {turn.toolCalls.length ? (
        <Text style={styles.meta}>tools: {turn.toolCalls.join(", ")}</Text>
      ) : null}
      {turn.costCents > 0 ? <Text style={styles.meta}>cost: {turn.costCents}¢</Text> : null}
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
  errorText: { color: colors.danger, fontSize: 13, marginBottom: 8 },
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
  },
  input: {
    flex: 1,
    backgroundColor: colors.haze,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
    fontSize: 15,
    color: colors.ink,
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
});
