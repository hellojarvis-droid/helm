import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { colors } from "@/lib/colors";
import { supabase } from "@/lib/supabase";

/**
 * Root layout. Gates rendering on a first auth check so we don't flash
 * the protected tabs before Supabase hydrates the session from AsyncStorage.
 */
export default function RootLayout() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // One-shot: resolve as soon as Supabase tells us the persisted session
    // (if any) is loaded. Subsequent auth state changes re-route via the
    // individual screens that call `getSession`.
    supabase()
      .auth.getSession()
      .finally(() => setReady(true));
  }, []);

  if (!ready) return null;

  return (
    <>
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
    </>
  );
}
