# 투자성향 진단 저장·조회 API 계약

## 경계

- 엔진 `evaluate_profile()`이 설문 채점의 단일 출처다. API·DB는 점수를 다시 계산하지 않는다.
- 인증된 사용자 UUID만 소유자로 사용한다. 요청 body에 `owner_id`를 받지 않는다.
- 진단·답변·확인 상태는 RAG 또는 embedding에 적재하지 않는다.

## POST `/me/investment-profile`

요청 body는 기존 엔진 입력을 감싼 API 전용 형태다.

```json
{
  "survey": {"answers": [{"question_code": "investment_horizon", "selected_score": 3}]},
  "investment_advice_desired": true,
  "investor_information_provided": true
}
```

실제 요청에는 엔진이 요구하는 6개 문항을 정확히 한 번씩 포함한다. `investor_information_provided=false`와 `investment_advice_desired=true` 조합은 422로 거부한다.

성공 시 assessment 1건, DB 질문·선택지 원본을 스냅샷한 answer 6건, append-only confirmation 1건을 하나의 트랜잭션으로 저장한다.

## GET `/me/investment-profile`

인증된 사용자의 최신 assessment만 반환한다. 미진단은 정상 초기 상태이므로 200으로 다음을 반환한다.

```json
{"assessment": null, "preferences": null}
```

## 유효기간 정책

- 정책 버전: `2026-07-20.1`
- 기간: 진단일(KST)부터 24개월
- 마지막 유효일: `진단일 + 24개월 - 1일`
- 만료: KST 기준 현재 날짜가 마지막 유효일보다 뒤인 경우
- DB 만료일 컬럼은 만들지 않으며 `assessed_at`으로 계산한다.

## 저장 테이블

`investment_profile_confirmations`는 `assessment_id`에 1:1로 연결된 append-only 확인 이력이다. RLS는 인증 사용자 자신의 행 SELECT/INSERT만 허용하고 UPDATE 정책은 만들지 않는다. 이 migration은 원격 적용 승인 전까지 `LOCAL-DRAFT`다.
