import * as Notifications from "expo-notifications";
import { Stack, useRouter, useSegments } from "expo-router";
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
  const [signedIn, setSignedIn] = useState(false);
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    const client = supabase();
    client.auth
      .getSession()
      .then(({ data }) => {
        const hasSession = Boolean(data.session);
        setSignedIn(hasSession);
        if (hasSession) void registerForPushNotifications();
      })
      .finally(() => setReady(true));

    const { data: listener } = client.auth.onAuthStateChange((_event, session) => {
      const hasSession = Boolean(session);
      setSignedIn(hasSession);
      if (hasSession) void registerForPushNotifications();
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const onSignIn = segments[0] === "sign-in";
    if (!signedIn && !onSignIn) {
      router.replace("/sign-in");
    } else if (signedIn && onSignIn) {
      router.replace("/(tabs)/chat");
    }
  }, [ready, router, segments, signedIn]);

  // Deep-link pushes: when the user taps a push with type=approval_requested,
  // jump to the exact approval when possible, otherwise the Approvals tab.
  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener((resp) => {
      const data = resp.notification.request.content.data as
        | { type?: string; approval_id?: unknown }
        | undefined;
      if (data?.type === "approval_requested") {
        if (typeof data.approval_id === "string") {
          router.push({ pathname: "/approval/[id]", params: { id: data.approval_id } });
        } else {
          router.push({ pathname: "/(tabs)/approvals" });
        }
      }
    });
    return () => sub.remove();
  }, [router]);

  if (!ready) return null;
  if (!signedIn && segments[0] !== "sign-in") return null;

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
          <Stack.Screen name="approval/[id]" options={{ headerBackTitle: "Back" }} />
        </Stack>
      </PostHogProvider>
    </ErrorBoundary>
  );
}
