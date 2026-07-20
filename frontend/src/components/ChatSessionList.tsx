import { type ReactNode } from "react";

import type { ChatSessionSummary } from "../api/types";

interface ChatSessionListProps {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  deletingSessionId: string | null;
  historyLoading: boolean;
  isSending: boolean;
  onOpen: (sessionId: string) => void;
  onDelete: (session: ChatSessionSummary) => void;
  trashIcon: ReactNode;
}

export function ChatSessionList({
  sessions,
  activeSessionId,
  deletingSessionId,
  historyLoading,
  isSending,
  onOpen,
  onDelete,
  trashIcon,
}: ChatSessionListProps) {
  if (historyLoading && sessions.length === 0) {
    return <p className="auth-note">대화 이력을 불러오는 중...</p>;
  }
  if (sessions.length === 0) return <p className="auth-note">아직 저장된 대화가 없습니다.</p>;

  return (
    <div className="history-list">
      {sessions.map((session) => {
        const title = session.title || "새 대화";
        const deleting = deletingSessionId === session.session_id;
        const disabled = historyLoading || isSending || deletingSessionId !== null;
        return (
          <div className={`history-item ${activeSessionId === session.session_id ? "active" : ""}`} key={session.session_id}>
            <button className="history-open" data-session-id={session.session_id} type="button" onClick={() => onOpen(session.session_id)} disabled={disabled}>
              <strong>{title}</strong>
              <small>{new Date(session.updated_at).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })}</small>
            </button>
            <button className="history-delete" type="button" aria-label={`대화 삭제: ${title}`} title="대화 삭제" onClick={() => onDelete(session)} disabled={disabled}>
              {deleting ? "…" : trashIcon}
            </button>
          </div>
        );
      })}
    </div>
  );
}
