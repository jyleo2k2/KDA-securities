import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { getSupabaseClient, isSupabaseConfigured } from "./supabase";

interface SupabaseAuthState {
  configured: boolean;
  loading: boolean;
  session: Session | null;
  error: string | null;
  signIn: (email: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
}

export function useSupabaseAuth(): SupabaseAuthState {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(isSupabaseConfigured);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = getSupabaseClient();
    if (!supabase) {
      setLoading(false);
      return;
    }

    let active = true;
    void supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      setSession(data.session);
      setError(sessionError?.message ?? null);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (active) {
        setSession(nextSession);
        setLoading(false);
      }
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  async function signIn(email: string, password: string): Promise<boolean> {
    const supabase = getSupabaseClient();
    if (!supabase) {
      setError("Supabase 환경변수가 설정되지 않았습니다.");
      return false;
    }
    setLoading(true);
    setError(null);
    const { data, error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    setLoading(false);
    if (signInError) {
      setError(signInError.message);
      return false;
    }
    setSession(data.session);
    return true;
  }

  async function signOut(): Promise<void> {
    const supabase = getSupabaseClient();
    setError(null);
    await supabase?.auth.signOut();
    setSession(null);
  }

  return {
    configured: isSupabaseConfigured,
    loading,
    session,
    error,
    signIn,
    signOut,
  };
}
