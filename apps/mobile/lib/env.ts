import Constants from "expo-constants";

/**
 * Typed env accessor for mobile. Expo surfaces env at build time via
 * `EXPO_PUBLIC_*` vars; at runtime they live on `Constants.expoConfig.extra`
 * (if configured) or `process.env` on web. We prefer process.env because
 * `EXPO_PUBLIC_*` vars are replaced at bundle time by the Metro bundler.
 */
interface MobileEnv {
  supabaseUrl: string;
  supabaseAnonKey: string;
  helmApiBase: string;
}

let _cached: MobileEnv | null = null;

export function mobileEnv(): MobileEnv {
  if (_cached) return _cached;

  const url = process.env.EXPO_PUBLIC_SUPABASE_URL ?? "";
  const key = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? "";
  const api = process.env.EXPO_PUBLIC_HELM_API_BASE ?? "http://localhost:8000";

  if (!url || !key) {
    const envType = typeof Constants.expoConfig?.extra === "object" ? "expoConfig.extra" : "env";
    throw new Error(
      `missing EXPO_PUBLIC_SUPABASE_URL or EXPO_PUBLIC_SUPABASE_ANON_KEY (checked ${envType}). ` +
        `Create apps/mobile/.env and set them; restart the dev server so Metro picks them up.`,
    );
  }

  _cached = { supabaseUrl: url, supabaseAnonKey: key, helmApiBase: api };
  return _cached;
}
