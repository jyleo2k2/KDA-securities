# ETF 종목 이벤트 마스터 계약

> 기준일: 2026-07-16  
> 용도: 연금계좌 적격 ETF의 총수익률·변동성·리밸런싱 계산에서 종목 이벤트를 설명 가능하게 반영

## 결과 파일

```text
data/cache/events/etf_corporate_events_2026-07-16.json
```

현금 분배, 정확한 분배락일, 한투 수정주가의 명시적 분할·병합·합병 이벤트를 하나의
증빙 구조로 결합한다. 가격 급변만으로 종목 이벤트를 추정하지 않는다.

## 원천과 우선순위

1. 현금 분배액·지급기준일·지급일: KIND `ETF이익금분배 신고`
2. 정확한 분배락일·기준가격: KIND `ETF 분배락 기준가격 안내`의 `적용일`
3. 배당 일정 교차검증: 한투 `예탁원정보(배당일정)`
   (`/uapi/domestic-stock/v1/ksdinfo/dividend`, TR `HHKDB669102C0`)
4. 배당 내역 교차검증: 금융위원회 `주식배당정보`
   (`GetStocDiviInfoService_V2/getDiviInfo_V2`)
5. 분할·병합·합병: 한투 수정주가 `mod_yn`, `prtt_rate`, `revl_issu_reas`
6. 한투 사유가 불명확한 이벤트: 확정하지 않고 `issuer_verification_required`

KIND는 ETF 현금흐름 계산의 권위 원천으로 유지한다. 한투는 ETF 단축코드와
배당기준일, 금융위원회는 ISIN과 배당기준일이 정확히 일치할 때만 금액·지급일을
교차검증한다. 보조 원천이 다르더라도 KIND 값을 자동 수정하지 않고
`source_conflict_review_required`를 기록한다.

KIND 검색 식별자는 ETF 단축코드의 마지막 `0`을 생략한 값이다. 예를 들어 `006950`은
`069500`, `0015E`는 `0015E0`으로 정규화한 뒤 현금 분배 공시와 연결한다. 같은 코드의
분배락 적용일이 지급기준일과 같거나 7일 이내 선행할 때 가장 가까운 미사용 이벤트를
연결한다. 연결되지 않으면 지급기준일을 대체값으로 유지한다.

## 이벤트 필드

- `event_type`: `cash_distribution`, `split`, `reverse_split`, `merger`, 미분류 상태
- `effective_date`: 수익률 계산에 적용할 날짜
- `record_date`, `payment_date`, `cash_per_share_krw`, `ratio`
- `timing_basis`: 정확한 KIND 적용일 또는 지급기준일 대체
- `confidence`, `status`: 확정 수준과 추가 검증 필요 여부
- `source_evidence`: 접수번호, 원문 URL, 한투 원본 필드, 캐시 경로
- `cross_validation`: 일치한 보조 원천, 충돌 필드, 계산 권위 원천

한투 일정에만 있고 KIND 확정 공시가 없는 미래 이벤트는
`scheduled_cash_distribution`으로 분리한다. 이 이벤트의 기준일은 분배락일이
아니므로 과거 총수익률에 넣지 않고, 리밸런싱 전 예상 현금흐름 안내에만 사용한다.
분배금 또는 과거 분배율은 ETF 품질점수를 올리는 요인으로 사용하지 않는다. 분배금은
가격수익과 별개의 추가 수익이 아니라 총수익을 구성하는 현금흐름이기 때문이다.
금융위원회 데이터는 공공누리 제2유형(출처표시·상업적 이용금지)이므로 학습·발표
범위를 넘어 상업적으로 사용할 때는 한국예탁결제원과 별도 정보이용계약을 확인한다.

## 2026-07-16 결과

- KIND 현금 분배 이벤트: 8,048건
- KIND 분배락 검색: 8,047건
- KIND 분배락 원문 수집: 8,031건, 실패 16건
- 정확한 분배락일 연결: 8,029건
- 지급기준일 대체: 19건
- 미연결 분배락 공시: 2건
- 한투 수정주가 관측: 897,330건
- 한투 명시 이벤트: 0건

분배락 원문 실패 및 미연결 이벤트를 숨기지 않는다. 이후 원문이 확보되면 동일
접수번호 캐시를 다시 수집하고 마스터를 재생성한다.

## 실행

```powershell
uv --cache-dir .uv-cache run python -m backend.app.ingestion.kind_distribution_ex_dates `
  --from-date 2020-01-01 --to-date 2026-07-16 --workers 1

uv --cache-dir .uv-cache run python -m backend.app.etf_corporate_events `
  --as-of 2026-07-16 `
  --kis-dividend-schedule data/raw/kis/ksd_dividend_20260716.json `
  --fsc-stock-dividends data/raw/fsc/stock_dividends_20260716.json

uv --cache-dir .uv-cache run python -m backend.app.etf_cost_return_report `
  --as-of 2026-07-16 `
  --corporate-events data/cache/events/etf_corporate_events_2026-07-16.json
```

두 보조 파일 인자는 선택사항이다. 승인 키로 받은 실응답을 원본 JSON으로 보존한
뒤 전달하며, API 키 자체는 산출물·로그·명령행에 기록하지 않는다.
