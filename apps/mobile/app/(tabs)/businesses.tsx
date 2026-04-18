import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { createBusiness, listBusinesses, type Business } from "@/lib/api";
import { colors } from "@/lib/colors";

export default function BusinessesScreen() {
  const router = useRouter();
  const [rows, setRows] = useState<Business[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  async function refresh() {
    try {
      setRows(await listBusinesses());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <View style={styles.container}>
      <FlatList
        data={rows ?? []}
        keyExtractor={(b) => b.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <Row
            biz={item}
            onPress={() => router.push({ pathname: "/business/[id]", params: { id: item.id } })}
          />
        )}
        ListEmptyComponent={
          rows === null ? (
            <ActivityIndicator style={{ marginTop: 60 }} color={colors.iron} />
          ) : (
            <Text style={styles.empty}>
              No businesses yet. Create one to give the CEO Agent something to work on.
            </Text>
          )
        }
        ListHeaderComponent={error ? <Text style={styles.error}>{error}</Text> : null}
      />

      <Pressable style={styles.fab} onPress={() => setNewOpen(true)}>
        <Text style={styles.fabText}>+ New</Text>
      </Pressable>

      <NewBusinessModal
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={() => {
          setNewOpen(false);
          void refresh();
        }}
      />
    </View>
  );
}

function Row({ biz, onPress }: { biz: Business; onPress: () => void }) {
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <View>
        <Text style={styles.name}>{biz.name}</Text>
        <Text style={styles.vertical}>{biz.vertical}</Text>
      </View>
      <View style={styles.meta}>
        <Text style={styles.metaText}>${(biz.weekly_spend_cap_cents / 100).toFixed(0)}/wk</Text>
        <Text style={styles.metaText}>{biz.status}</Text>
      </View>
    </Pressable>
  );
}

function NewBusinessModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [vertical, setVertical] = useState("dtc_physical");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await createBusiness({ name: name.trim(), vertical });
      setName("");
      setVertical("dtc_physical");
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal visible={open} animationType="slide" onRequestClose={onClose} transparent>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalSheet}>
          <Text style={styles.modalTitle}>New business</Text>

          <Text style={styles.label}>Name</Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="Ember Candles"
            placeholderTextColor={colors.iron}
            style={styles.input}
          />

          <Text style={styles.label}>Vertical</Text>
          <View style={styles.pills}>
            {(["dtc_physical", "dtc_pod", "saas", "services"] as const).map((v) => (
              <Pressable
                key={v}
                style={[styles.pill, vertical === v && styles.pillActive]}
                onPress={() => setVertical(v)}
              >
                <Text style={[styles.pillText, vertical === v && styles.pillTextActive]}>{v}</Text>
              </Pressable>
            ))}
          </View>

          {err ? <Text style={styles.error}>{err}</Text> : null}

          <View style={styles.modalActions}>
            <Pressable style={styles.cancel} onPress={onClose} disabled={busy}>
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>
            <Pressable
              style={[styles.create, (!name.trim() || busy) && { opacity: 0.5 }]}
              onPress={submit}
              disabled={busy || !name.trim()}
            >
              {busy ? (
                <ActivityIndicator color={colors.paper} />
              ) : (
                <Text style={styles.createText}>Create</Text>
              )}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.paper },
  list: { padding: 16, gap: 10 },
  empty: {
    textAlign: "center",
    color: colors.iron,
    marginTop: 80,
    fontSize: 14,
    paddingHorizontal: 32,
  },
  error: { color: colors.danger, fontSize: 13, marginBottom: 12 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: colors.haze,
    padding: 16,
    borderRadius: 10,
  },
  name: { fontSize: 15, fontWeight: "500", color: colors.ink },
  vertical: { fontSize: 12, color: colors.iron, marginTop: 2 },
  meta: { alignItems: "flex-end" },
  metaText: { fontSize: 12, color: colors.iron, fontFamily: "Menlo" },
  fab: {
    position: "absolute",
    right: 16,
    bottom: 16,
    backgroundColor: colors.ink,
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 24,
    shadowColor: colors.ink,
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
  },
  fabText: { color: colors.paper, fontWeight: "500" },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  modalSheet: {
    backgroundColor: colors.paper,
    padding: 24,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    gap: 10,
  },
  modalTitle: { fontSize: 18, fontWeight: "600", color: colors.ink, marginBottom: 6 },
  label: { fontSize: 13, color: colors.ink },
  input: {
    backgroundColor: colors.haze,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
    fontSize: 15,
    color: colors.ink,
  },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  pill: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: colors.haze,
  },
  pillActive: { backgroundColor: colors.ink },
  pillText: { color: colors.ink, fontSize: 12 },
  pillTextActive: { color: colors.paper },
  modalActions: { flexDirection: "row", gap: 8, marginTop: 12 },
  cancel: { flex: 1, paddingVertical: 12, alignItems: "center", borderRadius: 8 },
  cancelText: { color: colors.iron, fontSize: 15 },
  create: {
    flex: 1,
    backgroundColor: colors.ink,
    paddingVertical: 12,
    alignItems: "center",
    borderRadius: 8,
  },
  createText: { color: colors.paper, fontSize: 15, fontWeight: "500" },
});
