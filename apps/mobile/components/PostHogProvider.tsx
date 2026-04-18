import Constants from "expo-constants";
import { PostHogProvider as Provider, usePostHog } from "posthog-react-native";
import { useEffect } from "react";
import { supabase } from "@/lib/supabase";

/**
 * PostHog provider — wraps the app when EXPO_PUBLIC_POSTHOG_KEY is
 * configured. No-op otherwise (Expo Go dev without PostHog stays silent).
 * Identifies the signed-in Supabase user and captures lifecycle events.
 */
export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const key =
    (Constants.expoConfig?.extra?.POSTHOG_KEY as string | undefined) ??
    process.env.EXPO_PUBLIC_POSTHOG_KEY;
  const host =
    (Constants.expoConfig?.extra?.POSTHOG_HOST as string | undefined) ??
    process.env.EXPO_PUBLIC_POSTHOG_HOST ??
    "https://us.i.posthog.com";

  if (!key) return <>{children}</>;

  return (
    <Provider
      apiKey={key}
      options={{ host, captureAppLifecycleEvents: true }}
      autocapture={{ captureScreens: true }}
    >
      <Identifier>{children}</Identifier>
    </Provider>
  );
}

function Identifier({ children }: { children: React.ReactNode }) {
  const posthog = usePostHog();
  useEffect(() => {
    if (!posthog) return;
    void supabase()
      .auth.getUser()
      .then(({ data }) => {
        const u = data.user;
        if (u) posthog.identify(u.id, u.email ? { email: u.email } : {});
      });
  }, [posthog]);
  return <>{children}</>;
}
