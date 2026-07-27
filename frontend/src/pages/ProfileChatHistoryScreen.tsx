import { useEffect, useRef, useState, type JSX } from "react";

import { getChatSessions, getStoredChatMessages } from "../api/client";
import type { ChatSessionSummary, StoredChatMessage } from "../api/types";
import { StatusBar } from "../components/StatusBar";
import "./ProfileChatHistoryScreen.css";

interface ProfileChatHistoryScreenProps {
  accessToken: string;
  onBack: () => void;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function ProfileChatHistoryScreen({
  accessToken,
  onBack,
}: ProfileChatHistoryScreenProps): JSX.Element {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<ChatSessionSummary | null>(null);
  const [messages, setMessages] = useState<StoredChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [messageLoading, setMessageLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ownerGenerationRef = useRef(0);
  const messageGenerationRef = useRef(0);

  useEffect(() => {
    const ownerGeneration = ++ownerGenerationRef.current;
    ++messageGenerationRef.current;
    let cancelled = false;
    setSessions([]);
    setSelectedSession(null);
    setMessages([]);
    setError(null);
    setLoading(true);

    if (!accessToken) {
      setLoading(false);
      return () => { cancelled = true; };
    }

    void getChatSessions(accessToken)
      .then((items) => {
        if (!cancelled && ownerGeneration === ownerGenerationRef.current) {
          setSessions(items);
        }
      })
      .catch(() => {
        if (!cancelled && ownerGeneration === ownerGenerationRef.current) {
          setError("대화 기록을 불러오지 못했어요.");
        }
      })
      .finally(() => {
        if (!cancelled && ownerGeneration === ownerGenerationRef.current) {
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [accessToken]);

  async function openSession(session: ChatSessionSummary): Promise<void> {
    const ownerGeneration = ownerGenerationRef.current;
    const messageGeneration = ++messageGenerationRef.current;
    setSelectedSession(session);
    setMessages([]);
    setError(null);
    setMessageLoading(true);
    try {
      const stored = await getStoredChatMessages(session.session_id, accessToken);
      if (
        ownerGeneration === ownerGenerationRef.current
        && messageGeneration === messageGenerationRef.current
      ) {
        setMessages(stored.filter((message) => (
          message.role === "user" || message.role === "assistant"
        )));
      }
    } catch {
      if (
        ownerGeneration === ownerGenerationRef.current
        && messageGeneration === messageGenerationRef.current
      ) {
        setError("선택한 대화를 불러오지 못했어요.");
      }
    } finally {
      if (
        ownerGeneration === ownerGenerationRef.current
        && messageGeneration === messageGenerationRef.current
      ) {
        setMessageLoading(false);
      }
    }
  }

  function handleBack(): void {
    if (selectedSession) {
      ++messageGenerationRef.current;
      setSelectedSession(null);
      setMessages([]);
      setError(null);
      return;
    }
    onBack();
  }

  return (
    <main className="app-phone-stage profile-chat-history-stage">
      <section
        className="app-phone-frame profile-chat-history-phone"
        aria-label="대화 기록"
      >
        <StatusBar />
        <header className="profile-chat-history-header">
          <button type="button" onClick={handleBack} aria-label="뒤로 가기">‹</button>
          <h1>{selectedSession?.title || "대화 기록"}</h1>
        </header>
        <div className="profile-chat-history-scroll">
          {!selectedSession && (
            <>
              <p className="profile-chat-history-intro">
                로그인한 계정으로 나눈 대화를 확인할 수 있어요.
              </p>
              {loading && <p className="profile-chat-history-state">대화 기록을 불러오는 중이에요.</p>}
              {error && <p className="profile-chat-history-state profile-chat-history-error">{error}</p>}
              {!loading && !error && sessions.length === 0 && (
                <div className="profile-chat-history-empty">
                  <strong>아직 저장된 대화가 없어요</strong>
                  <p>연금 가이드에서 대화를 시작하면 여기에 기록이 표시돼요.</p>
                </div>
              )}
              <div className="profile-chat-history-list">
                {sessions.map((session) => (
                  <button
                    type="button"
                    key={session.session_id}
                    onClick={() => { void openSession(session); }}
                  >
                    <span>
                      <strong>{session.title || "새 대화"}</strong>
                      <small>{formatDate(session.updated_at)}</small>
                    </span>
                    <b aria-hidden="true">›</b>
                  </button>
                ))}
              </div>
            </>
          )}
          {selectedSession && (
            <div className="profile-chat-history-detail">
              <p>{formatDate(selectedSession.updated_at)}</p>
              {messageLoading && (
                <p className="profile-chat-history-state">대화를 불러오는 중이에요.</p>
              )}
              {error && <p className="profile-chat-history-state profile-chat-history-error">{error}</p>}
              {!messageLoading && !error && messages.length === 0 && (
                <p className="profile-chat-history-state">표시할 대화 내용이 없어요.</p>
              )}
              {messages.map((message) => (
                <div
                  className={`profile-chat-history-message profile-chat-history-message--${message.role}`}
                  key={message.message_id}
                >
                  <span>{message.role === "user" ? "나" : "연금 KDA"}</span>
                  <p>{message.content}</p>
                  <small>{formatDate(message.created_at)}</small>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
