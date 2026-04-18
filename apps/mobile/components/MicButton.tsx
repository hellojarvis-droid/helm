import { Audio } from "expo-av";
import * as Haptics from "expo-haptics";
import { useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text } from "react-native";
import { transcribeAudio } from "@/lib/api";
import { colors } from "@/lib/colors";

/**
 * Hold-to-talk mic. Tap to start recording, tap again to stop and upload
 * to /chat/transcribe. Resolved text is handed back via onTranscribed.
 * Server-side gate: 501 from /transcribe (Whisper not configured) surfaces
 * via onError; the parent can hide the button after that.
 */
export function MicButton({
  onTranscribed,
  onError,
  disabled,
}: {
  onTranscribed: (text: string) => void;
  onError?: (message: string) => void;
  disabled?: boolean;
}) {
  const [state, setState] = useState<"idle" | "recording" | "uploading">("idle");
  const recordingRef = useRef<Audio.Recording | null>(null);

  async function start() {
    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        onError?.("microphone permission denied");
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
      );
      recordingRef.current = recording;
      setState("recording");
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : String(e));
      setState("idle");
    }
  }

  async function stop() {
    const rec = recordingRef.current;
    if (!rec) return;
    recordingRef.current = null;
    setState("uploading");
    Haptics.selectionAsync();
    try {
      await rec.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
      const uri = rec.getURI();
      if (!uri) {
        onError?.("recording returned no file");
        setState("idle");
        return;
      }
      const text = await transcribeAudio(uri);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      onTranscribed(text);
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      onError?.(e instanceof Error ? e.message : String(e));
    } finally {
      setState("idle");
    }
  }

  function onPress() {
    if (state === "idle") void start();
    else if (state === "recording") void stop();
    // uploading state ignores taps
  }

  const label = state === "recording" ? "■" : state === "uploading" ? "" : "🎙";
  return (
    <Pressable
      style={[
        styles.button,
        state === "recording" && styles.recording,
        disabled && { opacity: 0.4 },
      ]}
      onPress={onPress}
      disabled={disabled || state === "uploading"}
      accessibilityLabel={state === "recording" ? "Stop recording" : "Start voice input"}
    >
      {state === "uploading" ? (
        <ActivityIndicator color={colors.paper} size="small" />
      ) : (
        <Text style={styles.label}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: colors.haze,
    width: 44,
    height: 44,
    borderRadius: 22,
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
  },
  recording: {
    backgroundColor: colors.danger,
    borderColor: colors.danger,
  },
  label: { fontSize: 18, color: colors.ink },
});
