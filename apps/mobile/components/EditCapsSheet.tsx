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
  const [mcc, setMcc] = useState(business.allowed_mcc_codes?.join(", ") ?? "");
  const [useDefaultMcc, setUseDefaultMcc] = useState(business.allowed_mcc_codes === null);
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
    const body: Parameters<typeof updateBusiness>[1] = {
      weekly_spend_cap_cents: weeklyCents,
      per_auth_cap_cents: perAuthCents,
    };
    if (useDefaultMcc) {
      body.reset_mcc_codes_to_default = true;
    } else {
      const codes = mcc
        .split(/[\s,]+/)
        .map((c) => c.trim())
        .filter(Boolean);
      if (codes.some((c) => !/^\d{3,4}$/.test(c))) {
        setError("MCC codes must be 3-4 digit numbers.");
        return;
      }
      body.allowed_mcc_codes = codes;
    }
    setBusy(true);
    setError(null);
    Haptics.selectionAsync();
    try {
      const updated = await updateBusiness(business.id, body);
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

          <View style={styles.mccHeaderRow}>
            <Text style={styles.label}>Allowed MCC codes</Text>
            <Pressable onPress={() => setUseDefaultMcc((v) => !v)}>
              <Text style={[styles.toggle, useDefaultMcc && styles.toggleOn]}>
                {useDefaultMcc ? "✓ Default" : "Custom"}
              </Text>
            </Pressable>
          </View>
          <TextInput
            value={mcc}
            onChangeText={setMcc}
            editable={!useDefaultMcc}
            placeholder="5734, 7372, 7311"
            placeholderTextColor={colors.iron}
            style={[styles.mccInput, useDefaultMcc && { opacity: 0.5 }]}
          />
          <Text style={styles.mccHint}>
            Comma-separated 4-digit codes. Default covers SaaS, ads, POD suppliers.
          </Text>

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
  mccHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginTop: 8,
  },
  toggle: {
    fontSize: 11,
    color: colors.iron,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  toggleOn: {
    color: colors.accent,
    borderColor: colors.accent,
  },
  mccInput: {
    backgroundColor: colors.haze,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: colors.ink,
    fontFamily: "Menlo",
  },
  mccHint: {
    fontSize: 11,
    color: colors.iron,
    lineHeight: 15,
    marginTop: 4,
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
