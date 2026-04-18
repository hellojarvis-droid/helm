import * as Haptics from "expo-haptics";
import { useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { updateBusiness, type BusinessDetail } from "@/lib/api";
import { colors } from "@/lib/colors";

export function EditCapsSheet({
  open,
  business,
  onClose,
  onSaved,
}: {
  open: boolean;
  business: BusinessDetail;
  onClose: () => void;
  onSaved: (updated: BusinessDetail) => void;
}) {
  const [weekly, setWeekly] = useState((business.weekly_spend_cap_cents / 100).toFixed(0));
  const [perAuth, setPerAuth] = useState((business.per_auth_cap_cents / 100).toFixed(0));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const weeklyCents = Math.round(Number(weekly) * 100);
    const perAuthCents = Math.round(Number(perAuth) * 100);
    if (!Number.isFinite(weeklyCents) || weeklyCents < 0) {
      setError("Weekly cap must be a non-negative number.");
      return;
    }
    if (!Number.isFinite(perAuthCents) || perAuthCents < 0) {
      setError("Per-auth cap must be a non-negative number.");
      return;
    }
    setBusy(true);
    setError(null);
    Haptics.selectionAsync();
    try {
      const updated = await updateBusiness(business.id, {
        weekly_spend_cap_cents: weeklyCents,
        per_auth_cap_cents: perAuthCents,
      });
      const syncOk = !updated.stripe_sync?.attempted || updated.stripe_sync?.synced === true;
      Haptics.notificationAsync(
        syncOk
          ? Haptics.NotificationFeedbackType.Success
          : Haptics.NotificationFeedbackType.Warning,
      );
      onSaved(updated);
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal visible={open} animationType="slide" onRequestClose={onClose} transparent>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <Text style={styles.title}>Edit spend caps</Text>
          <Text style={styles.desc}>
            Caps are enforced at our authorization webhook AND on the Stripe card itself. Changes
            push to both.
          </Text>

          <Text style={styles.label}>Weekly cap</Text>
          <View style={styles.inputRow}>
            <Text style={styles.dollar}>$</Text>
            <TextInput
              value={weekly}
              onChangeText={setWeekly}
              keyboardType="numeric"
              style={styles.input}
            />
          </View>

          <Text style={styles.label}>Per-authorization cap</Text>
          <View style={styles.inputRow}>
            <Text style={styles.dollar}>$</Text>
            <TextInput
              value={perAuth}
              onChangeText={setPerAuth}
              keyboardType="numeric"
              style={styles.input}
            />
          </View>

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <View style={styles.actions}>
            <Pressable style={styles.cancel} onPress={onClose} disabled={busy}>
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>
            <Pressable
              style={[styles.save, busy && { opacity: 0.6 }]}
              onPress={save}
              disabled={busy}
            >
              {busy ? (
                <ActivityIndicator color={colors.paper} />
              ) : (
                <Text style={styles.saveText}>Save</Text>
              )}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: colors.paper,
    padding: 20,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    gap: 8,
  },
  title: { fontSize: 18, fontWeight: "600", color: colors.ink },
  desc: { fontSize: 12, color: colors.iron, lineHeight: 17, marginBottom: 8 },
  label: {
    fontSize: 11,
    color: colors.iron,
    textTransform: "uppercase",
    letterSpacing: 1,
    fontWeight: "600",
    marginTop: 8,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.haze,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  dollar: { fontSize: 20, color: colors.ink, fontFamily: "Menlo" },
  input: {
    flex: 1,
    fontSize: 18,
    color: colors.ink,
    fontFamily: "Menlo",
    padding: 0,
  },
  error: { color: colors.danger, fontSize: 13, marginTop: 4 },
  actions: { flexDirection: "row", gap: 8, marginTop: 16 },
  cancel: {
    flex: 1,
    paddingVertical: 12,
    alignItems: "center",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
  },
  cancelText: { color: colors.iron, fontSize: 15, fontWeight: "500" },
  save: {
    flex: 1,
    backgroundColor: colors.accent,
    paddingVertical: 12,
    alignItems: "center",
    borderRadius: 8,
  },
  saveText: { color: colors.paper, fontSize: 15, fontWeight: "500" },
});
