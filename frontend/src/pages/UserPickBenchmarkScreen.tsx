import { useEffect, useRef, useState, type JSX } from "react";

import {
  getBenchmarkFollows,
  getDemoHeroes,
  getMyPensionContext,
  setBenchmarkFollow,
} from "../api/client";
import type { BenchmarkFollowState } from "../api/types";
import { supabase } from "../auth/supabase";
import "./UserPickBenchmarkScreen.css";

interface UserPickBenchmarkScreenProps {
  onBack: () => void;
}

// 상세 화면의 뒤로가기는 iframe 내부에서 목록으로 복귀한다(closeDetail).
// 목록 화면의 뒤로가기만 이 메시지로 부모에게 홈 이탈을 요청한다.
export function UserPickBenchmarkScreen({ onBack }: UserPickBenchmarkScreenProps): JSX.Element {
  const onBackRef = useRef(onBack);
  useEffect(() => { onBackRef.current = onBack; }, [onBack]);

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const accessTokenRef = useRef<string | null>(null);
  const followStatesRef = useRef<BenchmarkFollowState[]>([]);
  const pendingPortfolioIdsRef = useRef(new Set<string>());
  const [ownerReturnPct, setOwnerReturnPct] = useState<number | null>(null);
  const [followStates, setFollowStates] = useState<BenchmarkFollowState[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function loadBenchmarkContext(): Promise<void> {
      if (!supabase) return;

      try {
        const { data } = await supabase.auth.getSession();
        const accessToken = data.session?.access_token;
        if (!accessToken) return;
        accessTokenRef.current = accessToken;

        const [ownerResult, followResult] = await Promise.allSettled([
          Promise.all([
            getMyPensionContext(accessToken),
            getDemoHeroes(accessToken),
          ]),
          getBenchmarkFollows(accessToken),
        ]);

        if (!cancelled && ownerResult.status === "fulfilled") {
          const [context, heroes] = ownerResult.value;
          const ownerHero = heroes.find(
            (hero) => hero.scenario_code === context.scenario_code,
          );
          const returnPct = Number(
            ownerHero?.past_performance.trailing_12m_return_pct,
          );
          if (Number.isFinite(returnPct)) setOwnerReturnPct(returnPct);
        }

        if (!cancelled && followResult.status === "fulfilled") {
          followStatesRef.current = followResult.value;
          setFollowStates(followResult.value);
        }
      } catch {
        if (!cancelled) {
          setOwnerReturnPct(null);
          followStatesRef.current = [];
          setFollowStates([]);
        }
      }
    }

    void loadBenchmarkContext();
    return () => { cancelled = true; };
  }, []);

  function sendOwnerReturn(): void {
    if (ownerReturnPct === null) return;
    iframeRef.current?.contentWindow?.postMessage(
      {
        type: "benchmark-owner-return",
        trailing12mReturnPct: ownerReturnPct,
      },
      window.location.origin,
    );
  }

  useEffect(sendOwnerReturn, [ownerReturnPct]);

  function sendFollowStates(items = followStatesRef.current): void {
    iframeRef.current?.contentWindow?.postMessage(
      {
        type: "benchmark-follow-state",
        items,
      },
      window.location.origin,
    );
  }

  useEffect(() => {
    followStatesRef.current = followStates;
    sendFollowStates(followStates);
  }, [followStates]);

  useEffect(() => {
    function handleMessage(event: MessageEvent): void {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (event.origin !== window.location.origin) return;

      const message = event.data as {
        type?: string;
        portfolioId?: unknown;
        following?: unknown;
      } | null;
      if (message?.type === "benchmark-html-back") {
        onBackRef.current();
        return;
      }
      if (
        message?.type !== "benchmark-follow-toggle"
        || typeof message.portfolioId !== "string"
        || typeof message.following !== "boolean"
      ) return;

      const accessToken = accessTokenRef.current;
      const portfolioId = message.portfolioId;
      if (!accessToken || pendingPortfolioIdsRef.current.has(portfolioId)) return;

      pendingPortfolioIdsRef.current.add(portfolioId);
      void setBenchmarkFollow(portfolioId, message.following, accessToken)
        .then((updated) => {
          const next = followStatesRef.current.some(
            (item) => item.portfolio_id === updated.portfolio_id,
          )
            ? followStatesRef.current.map((item) => (
              item.portfolio_id === updated.portfolio_id ? updated : item
            ))
            : [...followStatesRef.current, updated];
          followStatesRef.current = next;
          setFollowStates(next);
        })
        .catch(() => {
          sendFollowStates();
        })
        .finally(() => {
          pendingPortfolioIdsRef.current.delete(portfolioId);
        });
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  function handleIframeLoad(): void {
    sendOwnerReturn();
    sendFollowStates();
  }

  return (
    <main className="app-phone-stage benchmark-html-stage">
      <section className="app-phone-frame benchmark-html-frame-wrap" aria-label="투자 벤치마킹하기">
        <iframe
          ref={iframeRef}
          className="benchmark-html-frame"
          onLoad={handleIframeLoad}
          src="/benchmark-html/투자 벤치마킹.dc.html"
          title="투자 벤치마킹하기"
        />
      </section>
    </main>
  );
}
