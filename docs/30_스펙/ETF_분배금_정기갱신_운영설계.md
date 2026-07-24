# ETF 분배금 이벤트 정기 갱신 운영 설계

> 상태: 설계안 — 구현·원격 실행 전 승인 필요  
> 대상: KIND 현금분배·분배락 공시, 한국투자증권 KSD 배당일정, 기존 ETF 이벤트 마스터

## 1. 목표와 범위

공식 ETF 분배금 이벤트를 정기 수집해 챗봇의 분배금 일정·재투자 교육 안내에 반영한다.
KIND 현금분배 공시는 과거 총수익률과 확정 현금흐름의 계산 권위이고, KIS KSD 일정은
예정 일정의 참고 근거다. 이 작업은 자동 주문, 자동 재투자, 미래 수익 예측을 만들지 않는다.

현재 `data/raw/`·`data/cache/`는 Git에서 제외된다. GitHub Actions의 임시 디스크만으로
정기 갱신하면 과거 근거가 사라져 새 버전이 기존 이력을 덮어쓸 수 있다. 따라서 원본 보존과
정규화·적재를 분리한다.

## 2. 확정 데이터 규칙

| 구분 | 원천 | 사용 | 상태 |
|---|---|---|---|
| 확정 현금분배 | KIND 이익금분배 공시 | 과거 총수익률, 리밸런싱 가능 현금 | `confirmed_cash_flow` |
| 정확 분배락일 | KIND 분배락 기준가격 공시 | 총수익률 적용일 | `exact_kind_ex_distribution_date` |
| 예정 일정 | KIS KSD 배당일정 | 챗봇 참고·현금흐름 안내만 | `excluded_from_historical_total_return` |
| 불일치 | KIND와 보조 원천 불일치 | 자동 보정 금지, 검토 대기 | `source_conflict_review_required` |

기존 [ETF 종목 이벤트 마스터 계약](./ETF_종목_이벤트_마스터_계약.md)의 필드와 원천 우선순위는
변경하지 않는다.

## 3. 권장 아키텍처

```text
KIND / KIS API
      │  원본 응답 + SHA-256 + 요청 기간
      ▼
비공개 원본 보관소 (Supabase Storage 권장)
      │  run manifest
      ▼
정규화·교차검증·증분 병합
      │  품질 게이트 통과 시에만
      ▼
etf_distribution_event_versions (loading → ready)
      │
      ├─ /market/etfs/{isu_code}/distribution-events
      └─ 챗봇 분배금 일정·재투자 교육 안내
```

### 원본 보관소

- 권장: 비공개 Supabase Storage 버킷 `official-etf-distribution-raw`.
- 경로: `runs/{run_id}/kind/...`, `runs/{run_id}/kis/...`, `runs/{run_id}/manifest.json`.
- manifest에는 원천 URL 또는 endpoint, 요청 기간, 수집 시각, SHA-256, 행 수, 실패 목록을
  보존한다. API 키·Bearer 토큰·응답 헤더의 비밀 값은 저장하지 않는다.
- GitHub Actions artifact는 보조 디버그 용도로만 사용하며, 재생성과 감사의 원본 저장소로는
  사용하지 않는다.

## 4. 증분 갱신 절차

1. 최신 `ready` 이벤트 버전의 기준일과 원본 manifest를 읽는다.
2. KIND 현금분배·분배락은 `max(2020-01-01, 최신 기준일 - 45일)`부터 당일까지 다시 수집한다.
   정정 공시를 반영하기 위한 45일 중첩 구간이다.
3. KIS KSD 일정은 당일부터 120일 앞까지, 현재 원격 ETF 유니버스의 적격 ETF 코드로 수집한다.
4. 새 원본을 보관소에 올린 뒤, 기존 확정 이벤트는 중첩 구간만 새 결과로 대체하고 그 밖의
   이력은 유지한다. 예정 일정은 새 KIS 결과로 교체한다.
5. KIND를 계산 권위로 하여 분배락일을 연결하고, KIS·금융위 보조 근거와 일치 여부만 기록한다.
6. 아래 품질 게이트를 통과한 결과만 기존 `load_etf_distribution_event_master()`로 적재한다.
   적재 실패 시 기존 `ready` 버전은 그대로 유지한다.

`etf_distribution_events.raw_payload`에는 정규화된 이벤트가 보존돼 있으므로 증분 병합의
기존 이력 입력으로 사용한다. 원본 HTML·JSON 재처리는 Storage manifest의 파일을 사용한다.

## 5. 품질 게이트와 실패 처리

| 게이트 | 실패 시 처리 |
|---|---|
| 원본 SHA-256·요청 기간·원천이 manifest에 존재 | run 중단, 적재 금지 |
| 이벤트에 ETF 코드·적용일·`source_evidence`가 존재 | run 중단, 적재 금지 |
| 중첩 구간의 확정 이벤트 수가 직전 버전 대비 30% 초과 감소하지 않음 | 검토 대기, 기존 ready 유지 |
| KIND/KIS 불일치 | KIND 값은 유지, 검토 상태로 기록 |
| KIS 예정 일정만 존재 | 참고용 상태로 적재, 총수익률 입력 제외 |
| 네트워크·원천 오류 | 전체 run 실패로 기록, 부분 적재 금지 |

## 6. 자동화 일정

- 처음에는 GitHub Actions `workflow_dispatch`만 제공해 원격 데이터·Storage·ready 버전을 E2E
  확인한다.
- 검증 후 평일 06:30 KST(월~금)로 전환한다. 장 마감 직후가 아니라 공시 반영 여유를 둔
  아침 실행이며, 실행이 겹치지 않도록 기존 뉴스 수집과 별도 concurrency group을 둔다.
- 필요한 GitHub Secrets: 기존 `DATABASE_URL`, `KIS_APP_KEY`, `KIS_APP_SECRET`와 원본
  Storage 쓰기용 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.
- Actions 로그에는 run ID·건수·기준일·SHA-256만 남기고 원문·시크릿은 출력하지 않는다.

## 7. 구현 단계

1. Storage adapter와 run manifest 계약·비공개 버킷/RLS를 추가한다.
2. 최신 ETF 유니버스에서 KIS 조회 대상을 읽고, KIND·KIS 결과를 증분 병합하는 오케스트레이터를
   만든다.
3. 고정 fixture로 중첩 정정·예정 일정·불일치·부분 실패의 단위 테스트를 추가한다.
4. 수동 workflow를 원격에서 한 번 실행하고, 새 `ready` 버전·API·챗봇 출처 칩을 E2E 검증한다.
5. 운영 승인 뒤 평일 cron을 켠다.

## 8. 구현 전 승인 항목

- Supabase Storage를 원본 보관소로 쓰는 것과 1년 보존 기간
- 평일 06:30 KST 실행 및 필요한 GitHub Secrets 등록
- 45일 KIND 정정 창, 120일 KIS 예정 일정 창, 30% 감소 격리 임계값

승인 전에는 Storage 버킷 생성, 시크릿 등록, 원격 적재, cron 활성화를 수행하지 않는다.
