import { StyleSheet, Text, View } from "react-native";
import { colors } from "@/lib/colors";
import { useKillSwitch } from "@/lib/useKillSwitch";

/**
 * Danger-red strip rendered at the top of every tab that wants to
 * surface the global kill-switch state. Renders nothing when agents
 * are running normally.
 */
export function PausedBanner() {
  const { active } = useKillSwitch();
  if (!active) return null;
  return (
    <View style={styles.banner}>
      <Text style={styles.text}>● All agents paused — open Safety to resume</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.danger,
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  text: {
    color: colors.paper,
    fontSize: 12,
    fontWeight: "600",
    letterSpacing: 0.5,
  },
});
