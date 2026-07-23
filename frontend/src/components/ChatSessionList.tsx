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
      <div className="history-list">
        {historyLoading && chatSessions.length === 0 ? (
          <p className="auth-note">지난 대화를 불러오고 있어요.</p>
        ) : chatSessions.length === 0 ? (
          <p className="auth-note">아직 나눈 대화가 없어요. 궁금한 점을 편하게 물어보세요.</p>
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
                {deleting ? <span>…</span> : (
                  <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none">
                    <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
                  </svg>
                )}
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
      {chatSessions.length > 0 && (
        <div className="history-delete-all-wrap">
          <button
            aria-label="전체 삭제"
            className="history-delete-all"
            type="button"
            onClick={onDeleteAll}
            disabled={historyLoading || isSending || deletingSessionId !== null || deletingAllSessions}
          >
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
            </svg>
            <span>{deletingAllSessions ? "정리 중" : "지난 대화 모두 삭제"}</span>
          </button>
        </div>
      )}
    </>
  );
}
