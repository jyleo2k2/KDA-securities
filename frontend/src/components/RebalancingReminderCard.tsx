import type { RebalancingReminderState } from "../api/types";

export function RebalancingReminderCard({ reminder, busy, onEnable, onComplete, onAsk }: { reminder: RebalancingReminderState; busy: boolean; onEnable: () => void; onComplete: () => void; onAsk: () => void }) {
  if (reminder.profile_required || !reminder.cadence) return null;
  const due = reminder.enabled && reminder.is_due;
  return <section className="rebalancing-reminder-card" aria-label="리밸런싱 점검 알림">
    <strong>{due ? "리밸런싱 점검 시점이에요" : `리밸런싱 ${reminder.cadence.review_interval_months}개월 점검`}</strong>
    <p>{reminder.cadence.rationale}</p>
    <div className="rebalancing-reminder-actions">
      {!reminder.enabled ? (
        <button className="rebalancing-reminder-button is-primary" type="button" onClick={onEnable} disabled={busy}>점검 알림 켜기</button>
      ) : !reminder.review_available ? (
        <p className="rebalancing-reminder-hint">연동된 계좌가 있어야 실제 비중을 점검할 수 있어요.</p>
      ) : (
        <>
          <button className="rebalancing-reminder-button is-primary" type="button" onClick={onAsk} disabled={busy}>챗봇에 점검 요청</button>
          {due && <button className="rebalancing-reminder-button is-secondary" type="button" onClick={onComplete} disabled={busy}>이번 점검 완료</button>}
        </>
      )}
    </div>
    <small>자동 주문·매매는 실행하지 않아요.</small>
  </section>;
}
