import * as Sentry from "@sentry/react-native";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "@/lib/colors";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
  eventId: string | null;
}

/**
 * Top-level error boundary. Catches render-time exceptions anywhere in
 * the tree, reports to Sentry (no-op without DSN), and shows a friendly
 * fallback with a Try again button that resets the boundary.
 *
 * Class component because hooks can't catch render errors — that's
 * what componentDidCatch is for.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null, eventId: null };

  static getDerivedStateFromError(error: Error): State {
    return { error, eventId: null };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    const eventId = Sentry.captureException(error, {
      extra: { componentStack: info.componentStack },
    });
    if (eventId) this.setState({ eventId });
  }

  reset = (): void => {
    this.setState({ error: null, eventId: null });
  };

  emailSupport = (): void => {
    const ref = this.state.eventId ?? "";
    const subject = ref ? `Helm error — reference ${ref}` : "Helm error";
    const body = ref
      ? `I hit an error on Helm. Error reference: ${ref}\n\nWhat I was trying to do:\n`
      : `I hit an error on Helm.\n\nWhat I was trying to do:\n`;
    const url = `mailto:support@helm.app?subject=${encodeURIComponent(
      subject,
    )}&body=${encodeURIComponent(body)}`;
    Linking.openURL(url).catch(() => undefined);
  };

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    const { eventId } = this.state;
    return (
      <View style={styles.container}>
        <Text style={styles.eyebrow}>Helm hit a wall</Text>
        <Text style={styles.title}>The app crashed.</Text>
        <Text style={styles.body}>
          We&apos;ve logged it. Try again — if it keeps happening, email support and we&apos;ll
          dig in.
        </Text>
        {eventId ? (
          <Text style={styles.errCode} selectable>
            Error reference: {eventId}
          </Text>
        ) : null}
        <View style={styles.buttonRow}>
          <Pressable style={styles.button} onPress={this.reset}>
            <Text style={styles.buttonText}>Try again</Text>
          </Pressable>
          <Pressable style={styles.buttonSecondary} onPress={this.emailSupport}>
            <Text style={styles.buttonSecondaryText}>Email support</Text>
          </Pressable>
        </View>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.paper,
    padding: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  eyebrow: {
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 2,
    color: colors.danger,
    textTransform: "uppercase",
    marginBottom: 12,
  },
  title: {
    fontSize: 24,
    fontWeight: "600",
    color: colors.ink,
    textAlign: "center",
    marginBottom: 12,
  },
  body: {
    fontSize: 14,
    color: colors.iron,
    textAlign: "center",
    lineHeight: 21,
    maxWidth: 320,
  },
  email: { color: colors.ink, fontWeight: "500" },
  errCode: {
    fontSize: 11,
    fontFamily: "Menlo",
    color: colors.iron,
    marginTop: 16,
    textAlign: "center",
  },
  buttonRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 24,
  },
  button: {
    backgroundColor: colors.accent,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 6,
  },
  buttonText: { color: colors.paper, fontWeight: "500", fontSize: 14 },
  buttonSecondary: {
    borderWidth: 1,
    borderColor: colors.iron,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 6,
  },
  buttonSecondaryText: { color: colors.ink, fontWeight: "500", fontSize: 14 },
});
