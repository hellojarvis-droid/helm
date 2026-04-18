import { z } from "zod";

/**
 * Typed env accessor. Throws loudly at first access if something required is
 * missing — better than a 404 or a nonsense runtime error three hops deep.
 *
 * Only NEXT_PUBLIC_* vars are safe to expose to the browser. Server-only
 * vars are read through process.env directly from server components / route
 * handlers so they can never leak into the client bundle.
 */
const clientSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
  NEXT_PUBLIC_HELM_API_BASE: z.string().url().default("http://localhost:8000"),
});

type ClientEnv = z.infer<typeof clientSchema>;

let _cached: ClientEnv | null = null;

export function clientEnv(): ClientEnv {
  if (_cached) return _cached;
  _cached = clientSchema.parse({
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    NEXT_PUBLIC_HELM_API_BASE: process.env.NEXT_PUBLIC_HELM_API_BASE,
  });
  return _cached;
}
