import type { RebalancingReminderState } from "../api/types";

export function RebalancingReminderCard({ reminder, busy, onEnable, onComplete, onAsk }: { reminder: RebalancingReminderState; busy: boolean; onEnable: () => void; onComplete: () => void; onAsk: () => void }) {
  if (reminder.profile_required || !reminder.cadence) return null;
  const due = reminder.enabled && reminder.is_due;
  return <section className="rebalancing-reminder-card" aria-label="리밸런싱 점검 알림">
    <strong>{due ? "리밸런싱 점검 시점이에요" : `리밸런싱 ${reminder.cadence.review_interval_months}개월 점검`}</strong>
    <p>{reminder.cadence.rationale}</p>
    {!reminder.enabled ? <button type="button" onClick={onEnable} disabled={busy}>점검 알림 켜기</button> : <div><button type="button" onClick={onAsk} disabled={busy}>챗봇에 점검 요청</button>{due && <button type="button" onClick={onComplete} disabled={busy}>이번 점검 완료</button>}</div>}
    <small>자동 주문·매매는 실행하지 않아요.</small>
  </section>;
}
