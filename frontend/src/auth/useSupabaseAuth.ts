import { useCallback, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { isSupabaseConfigured, supabase } from "./supabase";

const DEMO_LOGIN_DOMAIN = "@kda-demo.invalid";

export function normalizeLoginId(loginId: string): string {
  const value = loginId.trim();
  return value.includes("@") ? value : `${value}${DEMO_LOGIN_DOMAIN}`;
}

export interface SupabaseAuthState {
  session: Session | null;
  loading: boolean;
  configured: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export function useSupabaseAuth(): SupabaseAuthState {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(isSupabaseConfigured);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    let active = true;
    void supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      setSession(sessionError ? null : data.session);
      setError(sessionError ? "로그인 상태를 확인하지 못했습니다." : null);
      setLoading(false);
    }).catch(() => {
      if (!active) return;
      setSession(null);
      setError("로그인 상태를 확인하지 못했습니다.");
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (!active || event === "INITIAL_SESSION") return;
      setSession(nextSession);
      setLoading(false);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) {
      throw new Error("Supabase 로그인이 설정되지 않았습니다.");
    }
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: normalizeLoginId(email),
      password,
    });
    if (signInError) {
      setError("아이디 또는 비밀번호를 확인해 주세요.");
      throw new Error("아이디 또는 비밀번호를 확인해 주세요.");
    }
  }, []);

  const signOut = useCallback(async () => {
    if (!supabase) return;
    setError(null);
    const { error: signOutError } = await supabase.auth.signOut({
      scope: "local",
    });
    if (signOutError) {
      setError("로그아웃하지 못했습니다.");
      throw new Error("로그아웃하지 못했습니다.");
    }
    setSession(null);
    setLoading(false);
  }, []);

  return {
    session,
    loading,
    configured: isSupabaseConfigured,
    error,
    signIn,
    signOut,
  };
}
