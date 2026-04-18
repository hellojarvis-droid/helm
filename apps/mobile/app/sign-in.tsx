import { useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { colors } from "@/lib/colors";
import { supabase } from "@/lib/supabase";

export default function SignInScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const client = supabase();
      const { error } =
        mode === "signin"
          ? await client.auth.signInWithPassword({ email, password })
          : await client.auth.signUp({ email, password });
      if (error) {
        setErr(error.message);
        return;
      }
      router.replace("/(tabs)/chat");
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.form}>
        <Text style={styles.title}>Helm</Text>
        <Text style={styles.subtitle}>{mode === "signin" ? "Sign in." : "Create an account."}</Text>

        <Text style={styles.label}>Email</Text>
        <TextInput
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          style={styles.input}
          placeholderTextColor={colors.iron}
        />

        <Text style={styles.label}>Password</Text>
        <TextInput
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete={mode === "signin" ? "password" : "password-new"}
          style={styles.input}
          placeholderTextColor={colors.iron}
        />

        {err ? <Text style={styles.error}>{err}</Text> : null}

        <Pressable style={styles.button} onPress={submit} disabled={busy}>
          {busy ? (
            <ActivityIndicator color={colors.paper} />
          ) : (
            <Text style={styles.buttonText}>
              {mode === "signin" ? "Sign in" : "Create account"}
            </Text>
          )}
        </Pressable>

        <Pressable onPress={() => setMode(mode === "signin" ? "signup" : "signin")}>
          <Text style={styles.toggle}>
            {mode === "signin" ? "Need an account? Sign up." : "Already have one? Sign in."}
          </Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.paper,
    justifyContent: "center",
    padding: 24,
  },
  form: {
    backgroundColor: colors.haze,
    padding: 24,
    borderRadius: 12,
    gap: 12,
  },
  title: {
    fontSize: 28,
    fontWeight: "600",
    letterSpacing: -0.5,
    color: colors.ink,
  },
  subtitle: {
    fontSize: 14,
    color: colors.iron,
    marginBottom: 8,
  },
  label: { fontSize: 13, color: colors.ink },
  input: {
    backgroundColor: colors.paper,
    borderWidth: 1,
    borderColor: "rgba(107,107,107,0.3)",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.ink,
  },
  error: { color: colors.danger, fontSize: 13 },
  button: {
    backgroundColor: colors.ink,
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 8,
  },
  buttonText: { color: colors.paper, fontSize: 15, fontWeight: "500" },
  toggle: {
    textAlign: "center",
    color: colors.iron,
    fontSize: 13,
    marginTop: 4,
  },
});
