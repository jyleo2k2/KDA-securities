import { useEffect, useRef, useState, type JSX } from "react";

import {
  getBenchmarkFollows,
  getDemoHeroes,
  getMyPensionAccounts,
  getMyPensionContext,
  setBenchmarkFollow,
} from "../api/client";
import type { AssetClass, BenchmarkFollowState, UserPensionPortfolio } from "../api/types";
import { supabase } from "../auth/supabase";
import "./UserPickBenchmarkScreen.css";

interface UserPickBenchmarkScreenProps {
  onBack: () => void;
}

type OwnerAssetClass = Extract<
  AssetClass,
  "domestic_equity" | "global_equity" | "deposit" | "bond" | "cash"
>;

const OWNER_ALLOCATION_META: Record<OwnerAssetClass, { label: string; color: string }> = {
  domestic_equity: { label: "국내주식", color: "#2F8F6B" },
  global_equity: { label: "글로벌주식", color: "#3F7BC4" },
  deposit: { label: "원리금보장", color: "#D28A24" },
  bond: { label: "채권", color: "#D96F3D" },
  cash: { label: "현금성", color: "#7C5BC4" },
};

const OWNER_ASSET_CLASSES = Object.keys(OWNER_ALLOCATION_META) as OwnerAssetClass[];

type OwnerAllocation = {
  label: string;
  color: string;
  percent: number;
};

type OwnerPortfolio = {
  nickname: string;
  totalAmountKrw: number;
  allocations: OwnerAllocation[];
};

function buildOwnerPortfolio(
  nickname: string,
  portfolio: UserPensionPortfolio,
): OwnerPortfolio | null {
  const amounts = new Map<OwnerAssetClass, number>(
    OWNER_ASSET_CLASSES.map((assetClass) => [assetClass, 0]),
  );

  for (const account of portfolio.accounts) {
    for (const holding of account.holdings) {
      if (!(holding.asset_class in OWNER_ALLOCATION_META)) continue;
      const amount = Number(holding.amount_krw);
      if (!Number.isFinite(amount) || amount < 0) continue;
      const assetClass = holding.asset_class as OwnerAssetClass;
      amounts.set(assetClass, (amounts.get(assetClass) ?? 0) + amount);
    }
  }

  const totalAmountKrw = [...amounts.values()].reduce((sum, amount) => sum + amount, 0);
  if (totalAmountKrw <= 0) return null;

  return {
    nickname,
    totalAmountKrw,
    allocations: OWNER_ASSET_CLASSES
      .map((assetClass) => ({
        ...OWNER_ALLOCATION_META[assetClass],
        percent: (amounts.get(assetClass) ?? 0) / totalAmountKrw * 100,
      }))
      .filter((allocation) => allocation.percent > 0),
  };
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
  const [ownerPortfolio, setOwnerPortfolio] = useState<OwnerPortfolio | null>(null);
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

        const [contextResult, heroesResult, portfolioResult, followResult] = await Promise.allSettled([
          getMyPensionContext(accessToken),
          getDemoHeroes(accessToken),
          getMyPensionAccounts(accessToken),
          getBenchmarkFollows(accessToken),
        ]);

        if (
          !cancelled
          && contextResult.status === "fulfilled"
          && heroesResult.status === "fulfilled"
        ) {
          const context = contextResult.value;
          const heroes = heroesResult.value;
          const ownerHero = heroes.find(
            (hero) => hero.scenario_code === context.scenario_code,
          );
          const returnPct = Number(
            ownerHero?.past_performance.trailing_12m_return_pct,
          );
          if (Number.isFinite(returnPct)) setOwnerReturnPct(returnPct);
        }

        if (
          !cancelled
          && contextResult.status === "fulfilled"
          && portfolioResult.status === "fulfilled"
        ) {
          const context = contextResult.value;
          const portfolio = portfolioResult.value;
          setOwnerPortfolio(buildOwnerPortfolio(context.nickname, portfolio));
        }

        if (!cancelled && followResult.status === "fulfilled") {
          followStatesRef.current = followResult.value;
          setFollowStates(followResult.value);
        }
      } catch {
        if (!cancelled) {
          setOwnerReturnPct(null);
          setOwnerPortfolio(null);
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

  function sendOwnerPortfolio(): void {
    if (ownerPortfolio === null) return;
    iframeRef.current?.contentWindow?.postMessage(
      {
        type: "benchmark-owner-portfolio",
        ...ownerPortfolio,
      },
      window.location.origin,
    );
  }

  useEffect(sendOwnerPortfolio, [ownerPortfolio]);

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
    sendOwnerPortfolio();
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
