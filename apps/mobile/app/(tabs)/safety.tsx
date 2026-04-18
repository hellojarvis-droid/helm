import * as Haptics from "expo-haptics";
import { useState } from "react";
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "@/lib/colors";
import { useKillSwitch } from "@/lib/useKillSwitch";

export default function SafetyScreen() {
  const { active, busy, error, toggle } = useKillSwitch();
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function onToggle() {
    if (active === null) return;
    if (!active) {
      // Going active — require confirmation. This is load-bearing: a
      // misclick here halts every running agent across every business.
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
      setConfirmOpen(true);
      return;
    }
    // Going inactive — no confirmation needed, resuming is low-risk.
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await toggle(false);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    }
  }

  async function onConfirmPause() {
    setConfirmOpen(false);
    try {
      await toggle(true);
      // Three quick heavy taps so the user *feels* it happen — this is
      // the "everything stopped" moment and it should have weight.
      for (let i = 0; i < 3; i++) {
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
        await new Promise((r) => setTimeout(r, 80));
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    } catch {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    }
  }

  if (active === null) {
    return (
      <View style={[styles.container, { alignItems: "center", justifyContent: "center" }]}>
        <ActivityIndicator color={colors.iron} />
      </View>
    );
  }

  return (
    <View style={[styles.container, active && styles.containerActive]}>
      <View style={styles.inner}>
        <View style={styles.statusBlock}>
          <Text style={[styles.statusLabel, active && { color: colors.danger }]}>
            {active ? "PAUSED" : "ALL SYSTEMS GO"}
          </Text>
          <Text style={styles.statusDesc}>
            {active
              ? "Every agent across every business is halted. No tool calls, no spend, no sends. Webhooks will log but won't act until you resume."
              : "Agents are running normally. Flip this switch to halt every tool call across every business within one second."}
          </Text>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable
          style={[styles.bigButton, active ? styles.bigButtonResume : styles.bigButtonPause]}
          onPress={onToggle}
          disabled={busy}
        >
          {busy ? (
            <ActivityIndicator color={active ? colors.danger : colors.paper} />
          ) : (
            <Text style={[styles.bigButtonText, active && { color: colors.danger }]}>
              {active ? "Resume everything" : "Pause everything"}
            </Text>
          )}
        </Pressable>

        <View style={styles.notesBlock}>
          <Note title="Enforcement">
            Backend checks this before every tool call. Stripe authorizations on your issuing card
            decline while paused. Composio calls raise KillSwitchActivated before hitting any
            provider.
          </Note>
          <Note title="Latency">
            1-second worst case. The runtime caches with a 1s TTL and invalidates on flip, so the
            next tool call after a toggle reflects the new state.
          </Note>
        </View>
      </View>

      <ConfirmModal
        open={confirmOpen}
        onCancel={() => {
          Haptics.selectionAsync();
          setConfirmOpen(false);
        }}
        onConfirm={onConfirmPause}
      />
    </View>
  );
}

function Note({ title, children }: { title: string; children: string }) {
  return (
    <View style={styles.note}>
      <Text style={styles.noteTitle}>{title}</Text>
      <Text style={styles.noteBody}>{children}</Text>
    </View>
  );
}

function ConfirmModal({
  open,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal visible={open} animationType="fade" onRequestClose={onCancel} transparent>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalSheet}>
          <Text style={styles.modalTitle}>Pause every agent?</Text>
          <Text style={styles.modalBody}>
            This halts every running agent across every business within one second. In-flight tool
            calls may still finish but no new ones will start. Stripe authorizations on your issuing
            card will decline until you resume.
          </Text>
          <View style={styles.modalActions}>
            <Pressable style={styles.modalCancel} onPress={onCancel}>
              <Text style={styles.modalCancelText}>Cancel</Text>
            </Pressable>
            <Pressable style={styles.modalConfirm} onPress={onConfirm}>
              <Text style={styles.modalConfirmText}>Pause everything</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.paper },
  containerActive: { backgroundColor: "rgba(168,37,26,0.04)" },
  inner: { padding: 24, gap: 20, paddingTop: 40 },

  statusBlock: { gap: 8 },
  statusLabel: {
    fontSize: 22,
    fontWeight: "700",
    letterSpacing: 2,
    color: colors.success,
  },
  statusDesc: { fontSize: 14, color: colors.iron, lineHeight: 20 },
  error: { color: colors.danger, fontSize: 13 },

  bigButton: {
    paddingVertical: 20,
    borderRadius: 12,
    alignItems: "center",
    marginTop: 8,
  },
  bigButtonPause: {
    backgroundColor: colors.danger,
  },
  bigButtonResume: {
    backgroundColor: "transparent",
    borderWidth: 2,
    borderColor: colors.danger,
  },
  bigButtonText: {
    color: colors.paper,
    fontSize: 16,
    fontWeight: "600",
    letterSpacing: 0.5,
  },

  notesBlock: { gap: 12, marginTop: 12 },
  note: {
    backgroundColor: colors.haze,
    padding: 14,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.15)",
  },
  noteTitle: {
    fontSize: 11,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 1,
    color: colors.ink,
    marginBottom: 4,
  },
  noteBody: { fontSize: 13, color: colors.iron, lineHeight: 19 },

  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.6)",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  modalSheet: {
    backgroundColor: colors.paper,
    borderRadius: 14,
    padding: 20,
    width: "100%",
    maxWidth: 420,
    borderWidth: 1,
    borderColor: "rgba(168,37,26,0.3)",
  },
  modalTitle: {
    fontSize: 17,
    fontWeight: "600",
    color: colors.danger,
    marginBottom: 8,
  },
  modalBody: { fontSize: 13, color: colors.ink, lineHeight: 19, marginBottom: 16 },
  modalActions: { flexDirection: "row", gap: 8 },
  modalCancel: {
    flex: 1,
    paddingVertical: 12,
    alignItems: "center",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
  },
  modalCancelText: { color: colors.iron, fontSize: 14, fontWeight: "500" },
  modalConfirm: {
    flex: 1,
    backgroundColor: colors.danger,
    paddingVertical: 12,
    alignItems: "center",
    borderRadius: 8,
  },
  modalConfirmText: { color: colors.paper, fontSize: 14, fontWeight: "600" },
});
