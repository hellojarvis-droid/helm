import * as Sentry from "@sentry/react-native";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "@/lib/colors";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
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
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    Sentry.captureException(error, { extra: { componentStack: info.componentStack } });
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <View style={styles.container}>
        <Text style={styles.eyebrow}>Helm hit a wall</Text>
        <Text style={styles.title}>The app crashed.</Text>
        <Text style={styles.body}>
          We&apos;ve logged it. Try again — if it keeps happening, email{" "}
          <Text style={styles.email}>support@helm.app</Text>.
        </Text>
        {this.state.error.message ? (
          <Text style={styles.errCode}>{this.state.error.message.slice(0, 200)}</Text>
        ) : null}
        <Pressable style={styles.button} onPress={this.reset}>
          <Text style={styles.buttonText}>Try again</Text>
        </Pressable>
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
  button: {
    marginTop: 24,
    backgroundColor: colors.accent,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 6,
  },
  buttonText: { color: colors.paper, fontWeight: "500", fontSize: 14 },
});
