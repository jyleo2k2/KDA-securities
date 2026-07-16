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
3. 분할·병합·합병: 한투 수정주가 `mod_yn`, `prtt_rate`, `revl_issu_reas`
4. 한투 사유가 불명확한 이벤트: 확정하지 않고 `issuer_verification_required`

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
  --as-of 2026-07-16

uv --cache-dir .uv-cache run python -m backend.app.etf_cost_return_report `
  --as-of 2026-07-16 `
  --corporate-events data/cache/events/etf_corporate_events_2026-07-16.json
```
