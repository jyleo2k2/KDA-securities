import { useEffect, useState, type JSX } from "react";

import { getBenchmarkFollows } from "../api/client";
import type { BenchmarkFollowState } from "../api/types";
import { StatusBar } from "../components/StatusBar";
import {
  USER_PICK_PORTFOLIOS,
  type UserPickPortfolioPresentation,
} from "./userPickPortfolios";
import "./ProfileFollowingScreen.css";

interface ProfileFollowingScreenProps {
  accessToken: string;
  onBack: () => void;
}

interface FollowedPortfolio {
  presentation: UserPickPortfolioPresentation;
  followCount: number;
}

function formatFollowCount(value: number): string {
  return new Intl.NumberFormat("ko-KR").format(value);
}

export function ProfileFollowingScreen({
  accessToken,
  onBack,
}: ProfileFollowingScreenProps): JSX.Element {
  const [followed, setFollowed] = useState<FollowedPortfolio[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setFollowed([]);

    if (!accessToken) {
      setLoading(false);
      return () => { cancelled = true; };
    }

    void getBenchmarkFollows(accessToken)
      .then((states) => {
        if (cancelled) return;
        const stateById = new Map<string, BenchmarkFollowState>(
          states.map((state) => [state.portfolio_id, state]),
        );
        setFollowed(
          USER_PICK_PORTFOLIOS.flatMap((presentation) => {
            const state = stateById.get(presentation.id);
            return state?.is_following
              ? [{ presentation, followCount: state.follow_count }]
              : [];
          }),
        );
      })
      .catch(() => {
        if (!cancelled) setError("팔로우한 이용자를 불러오지 못했어요.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [accessToken]);

  return (
    <main className="app-phone-stage profile-following-stage">
      <section
        className="app-phone-frame profile-following-phone"
        aria-label="내가 팔로우한 이용자"
      >
        <StatusBar />
        <header className="profile-following-header">
          <button type="button" onClick={onBack} aria-label="내 페이지로 돌아가기">‹</button>
          <h1>내가 팔로우한 이용자</h1>
        </header>
        <div className="profile-following-scroll">
          {!loading && !error && followed.length > 0 && (
            <p className="profile-following-summary">
              <strong>{followed.length}명</strong>의 이용자를 팔로우하고 있어요
            </p>
          )}
          {loading && <p className="profile-following-state">목록을 불러오는 중이에요.</p>}
          {error && <p className="profile-following-state profile-following-error">{error}</p>}
          {!loading && !error && followed.length === 0 && (
            <div className="profile-following-empty">
              <strong>아직 팔로우한 이용자가 없어요</strong>
              <p>이용자 Pick에서 관심 있는 포트폴리오의 하트를 눌러보세요.</p>
            </div>
          )}
          <div className="profile-following-list">
            {followed.map(({ presentation, followCount }) => {
              return (
                <article className="profile-following-card" key={presentation.id}>
                  <div className="profile-following-card-top">
                    <div className="profile-following-identity">
                      <span>ID</span>
                      <strong>{presentation.id}</strong>
                      <span>직업군</span>
                      <b>{presentation.sector}</b>
                      <span>운용 기간</span>
                      <b>{presentation.period}</b>
                    </div>
                    <div className="profile-following-return">
                      <span>수익률</span>
                      <strong style={{ color: presentation.returnColor }}>
                        {presentation.returnLabel}
                      </strong>
                    </div>
                  </div>
                  <div className="profile-following-amount">
                    <span>금액</span>
                    <strong>{presentation.amount}</strong>
                  </div>
                  <div className="profile-following-count" aria-label={`팔로우 ${formatFollowCount(followCount)}`}>
                    <span aria-hidden="true">♥</span>
                    {formatFollowCount(followCount)}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    </main>
  );
}
