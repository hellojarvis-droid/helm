import * as Notifications from "expo-notifications";
import { Stack, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { PostHogProvider } from "@/components/PostHogProvider";
import { colors } from "@/lib/colors";
import { registerForPushNotifications } from "@/lib/push";
import { initSentry } from "@/lib/sentry";
import { supabase } from "@/lib/supabase";

// Sentry init at module load — captures errors from any code that runs
// before the first React render. Idempotent + silent no-op without DSN.
initSentry();

/**
 * Root layout. Gates rendering on a first auth check so we don't flash
 * the protected tabs before Supabase hydrates the session from AsyncStorage.
 */
export default function RootLayout() {
  const [ready, setReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    // One-shot: resolve as soon as Supabase tells us the persisted session
    // (if any) is loaded. Subsequent auth state changes re-route via the
    // individual screens that call `getSession`.
    supabase()
      .auth.getSession()
      .then(({ data }) => {
        if (data.session) void registerForPushNotifications();
      })
      .finally(() => setReady(true));
  }, []);

  // Deep-link pushes: when the user taps a push with type=approval_requested,
  // jump to the Approvals tab. The approval_id is in the payload for future
  // detail-view deep-links.
  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener((resp) => {
      const data = resp.notification.request.content.data as { type?: string } | undefined;
      if (data?.type === "approval_requested") {
        router.push({ pathname: "/(tabs)/approvals" });
      }
    });
    return () => sub.remove();
  }, [router]);

  if (!ready) return null;

  return (
    <ErrorBoundary>
      <PostHogProvider>
        <StatusBar style="auto" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.paper },
            headerTintColor: colors.ink,
            contentStyle: { backgroundColor: colors.paper },
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="sign-in" options={{ headerShown: false }} />
          <Stack.Screen name="business/[id]" options={{ headerBackTitle: "Back" }} />
        </Stack>
      </PostHogProvider>
    </ErrorBoundary>
  );
}
