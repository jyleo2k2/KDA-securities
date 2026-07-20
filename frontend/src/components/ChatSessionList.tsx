import type { ChatSessionSummary } from "../api/types";
import { ChatIcon } from "./ChatIcon";

export function ChatSessionList({
  activeSessionId,
  chatSessions,
  deleteStatus,
  deletingSessionId,
  historyLoading,
  isSending,
  onDelete,
  onLoad,
}: {
  activeSessionId: string | null;
  chatSessions: ChatSessionSummary[];
  deleteStatus: string | null;
  deletingSessionId: string | null;
  historyLoading: boolean;
  isSending: boolean;
  onDelete: (session: ChatSessionSummary) => void;
  onLoad: (sessionId: string) => void;
}) {
  return (
    <>
      <p className="sidebar-label history-label">저장된 대화</p>
      <div className="history-list">
        {historyLoading && chatSessions.length === 0 ? (
          <p className="auth-note">대화 이력을 불러오는 중...</p>
        ) : chatSessions.length === 0 ? (
          <p className="auth-note">아직 저장된 대화가 없습니다.</p>
        ) : chatSessions.map((session) => {
          const title = session.title || "새 대화";
          const deleting = deletingSessionId === session.session_id;
          const disabled = historyLoading || isSending || deletingSessionId !== null;
          return (
            <div
              className={`history-item ${activeSessionId === session.session_id ? "active" : ""}`}
              key={session.session_id}
            >
              <button
                className="history-open"
                data-session-id={session.session_id}
                type="button"
                onClick={() => onLoad(session.session_id)}
                disabled={disabled}
              >
                <strong>{title}</strong>
                <small>{new Date(session.updated_at).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })}</small>
              </button>
              <button
                className="history-delete"
                type="button"
                aria-label={`대화 삭제: ${title}`}
                title="대화 삭제"
                onClick={() => onDelete(session)}
                disabled={disabled}
              >
                {deleting ? "…" : <ChatIcon name="trash" size={14} />}
              </button>
            </div>
          );
        })}
      </div>
      {deleteStatus && (
        <p className="auth-note" role="status" aria-live="polite">
          {deleteStatus}
        </p>
      )}
    </>
  );
}
