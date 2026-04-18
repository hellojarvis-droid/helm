import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import "react-native-url-polyfill/auto";
import { mobileEnv } from "./env";

/**
 * RN Supabase client uses AsyncStorage so the session survives reloads.
 * One module-level instance — SDK is not event-loop-bound and holding a
 * single client avoids duplicate auth listeners.
 */
let _client: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
  if (_client) return _client;
  const env = mobileEnv();
  _client = createClient(env.supabaseUrl, env.supabaseAnonKey, {
    auth: {
      storage: AsyncStorage,
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: false, // no web-style OAuth redirects on RN
    },
  });
  return _client;
}
