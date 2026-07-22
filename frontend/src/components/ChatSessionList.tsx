import type { ChatSessionSummary } from "../api/types";

export function ChatSessionList({
  activeSessionId,
  chatSessions,
  deleteStatus,
  deletingAllSessions,
  deletingSessionId,
  historyLoading,
  isSending,
  onDelete,
  onDeleteAll,
  onLoad,
}: {
  activeSessionId: string | null;
  chatSessions: ChatSessionSummary[];
  deleteStatus: string | null;
  deletingAllSessions: boolean;
  deletingSessionId: string | null;
  historyLoading: boolean;
  isSending: boolean;
  onDelete: (session: ChatSessionSummary) => void;
  onDeleteAll: () => void;
  onLoad: (sessionId: string) => void;
}) {
  return (
    <>
      <div className="history-heading">
        <p className="sidebar-label history-label">저장된 대화</p>
        {chatSessions.length > 0 && (
          <button
            className="history-delete-all"
            type="button"
            onClick={onDeleteAll}
            disabled={historyLoading || isSending || deletingSessionId !== null || deletingAllSessions}
          >
            {deletingAllSessions ? "삭제 중" : "전체 삭제"}
          </button>
        )}
      </div>
      <div className="history-list">
        {historyLoading && chatSessions.length === 0 ? (
          <p className="auth-note">대화 이력을 불러오는 중...</p>
        ) : chatSessions.length === 0 ? (
          <p className="auth-note">아직 저장된 대화가 없습니다.</p>
        ) : chatSessions.map((session) => {
          const title = session.title || "새 대화";
          const deleting = deletingSessionId === session.session_id;
          const disabled = historyLoading || isSending || deletingSessionId !== null || deletingAllSessions;
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
                {deleting ? "…" : "삭제"}
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
