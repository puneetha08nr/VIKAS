import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Real client when env vars are present; stub when running without Supabase configured.
export const supabase: SupabaseClient = supabaseUrl && supabaseAnonKey
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: { flowType: "pkce", autoRefreshToken: true, persistSession: true },
    })
  : ({
      auth: {
        getSession: async () => ({ data: { session: null }, error: null }),
        signInWithPassword: async () => ({ data: {}, error: { message: "Supabase not configured. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY to .env.local" } }),
        signUp: async () => ({ data: {}, error: { message: "Supabase not configured." } }),
        signOut: async () => {},
        updateUser: async () => ({ data: {}, error: null }),
      },
    } as unknown as SupabaseClient);
