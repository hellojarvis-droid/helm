import Constants from "expo-constants";
import * as Sentry from "@sentry/react-native";

let initialized = false;

/**
 * Initialize Sentry once at app boot. Reads the DSN from
 * EXPO_PUBLIC_SENTRY_DSN — missing key is a silent no-op so Expo Go
 * dev without Sentry credentials stays quiet.
 *
 * Privacy: sendDefaultPii=false, no session-replay (RN replay is opt-in
 * via a separate integration; not enabled here until we revisit).
 */
export function initSentry(): void {
  if (initialized) return;
  const dsn =
    (Constants.expoConfig?.extra?.SENTRY_DSN as string | undefined) ??
    process.env.EXPO_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment:
      (Constants.expoConfig?.extra?.SENTRY_ENV as string | undefined) ??
      process.env.EXPO_PUBLIC_SENTRY_ENV ??
      "production",
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
    enableAutoSessionTracking: true,
  });
  initialized = true;
}
