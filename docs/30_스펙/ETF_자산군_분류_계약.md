# ETF 자산군 분류 계약

## 목적

KRX 현재 상장·관측충분 ETF 945개를 동일한 규칙으로 분류한다. 금융위원회 펀드상품기본정보와 정확히 연결되지 않은 상품도 KRX 기초지수와 한국투자증권 ETF 메타데이터를 이용해 분류하되, 추론과 공식 근거를 구분한다.

## 입력 소스

| 소스 | 사용 필드 |
|---|---|
| KRX | 종목코드, 종목명, 기초지수명 |
| 한국투자증권 | 대표지수명, ETF 업종명, 실물·합성·Active 구분, 구성종목코드·구성종목명·구성비, 상장통화 |
| 금융위원회 | 펀드명, 펀드유형, 상품분류코드, 펀드표준코드 |
| 금투협·운용사 공시 | 자동 규칙으로 확정되지 않는 환헤지·액티브 여부만 선택 검증 |

## 출력 필드

- `asset_class`: `equity`, `fixed_income`, `cash_equivalent`, `multi_asset`, `commodity`, `real_estate`, `currency`, `alternative`
- `sub_asset_class`: 국채·회사채·단기채·원유·금·리츠·TDF 등 세부유형
- `region`: 한국·미국·중국·일본·인도·유럽·글로벌 등
- `currency_hedge`: `hedged`, `unhedged`, `not_applicable`, `unknown`
- `management_style`: `active`, `passive`
- `replication_method`: `physical`, `synthetic`, `active_discretionary`
- `leverage_type`: `normal`, `leveraged`, `inverse`
- `strategy`: 광범위지수·테마·배당·팩터·커버드콜·TDF 등
- `classification_confidence`: 전체 분류의 `high`, `medium`, `low`
- `dimension_confidence`: 자산군·지역·환헤지·운용방식·복제방식별 신뢰도
- `decision_reasons`: 각 분류 차원의 직접 판정 근거
- `component_profile`: 구성종목 자산군·지역 비중, 지배 자산군, 기초지수와의 일치·충돌 상태
- `source_agreement`: 구성종목·금융위 정확 일치 펀드유형과 최종 분류의 일치·충돌 상태
- `disclosure_verification`: 공시 검증 여부·기준일·공시 URL·판정 문구
- `reason_codes`, `evidence`, `warnings`: 판단 근거와 추론 경고

## 판정 우선순위

자산군은 혼합·TDF, 리츠, 현금성, 통화, 원자재, 채권, 변동성, 주식 순으로 판정한다. 예를 들어 천연가스 밸류체인·원유생산기업은 관련기업 주식으로, 원유선물·GSCI 원유지수는 원자재로 구분한다.

한국투자증권의 `ETF(실물복제/수익증권)`, `ETF(합성복제/수익증권)`, `ETF(Active/수익증권)` 표기는 복제방식의 직접 근거로 사용한다. 필드가 단순 `ETF`이면 상품명의 `(합성)`과 `액티브`를 보조 근거로 사용하고 추론 경고를 남긴다.

## 구성종목 사용 원칙

- 한투가 반환한 모든 구성종목을 종목명 규칙으로 1차 분류하고 구성비를 자산군·지역별로 합산한다.
- 구성비 합계가 50% 이상이고 지배 자산군 비중이 70% 이상일 때만 기초지수 분류의 일치·충돌 신호로 사용한다.
- 구성종목이 기초지수와 일치하면 해당 차원의 신뢰도를 올린다.
- 선물·합성 ETF의 구성종목은 담보·대용자산일 수 있으므로 명시적인 기초지수 분류를 덮어쓰지 않는다. 충돌은 `warnings`와 `reason_codes`에 보존한다.
- 한투 구성종목 배열이 비어 있으면 누락 사실을 저장하고 기초지수·펀드유형·공시 근거로만 분류한다.
- 한투 `crcd=KRW`는 국내 상장 결제통화이지 해외 기초자산의 통화가 아니므로 환헤지 판정에 사용하지 않는다.

## 금융위원회 후보 사용 원칙

- 정규화 이름이 정확히 일치한 펀드는 공식 펀드유형을 직접 사용한다.
- 미일치 상품은 이름 유사도 0.92 이상이고 차순위와 0.03 이상 차이가 날 때만 `probable_name_candidate`로 표시한다.
- 유사 후보의 거친 자산군이 KRX·한투 분류와 일치할 때만 보조 근거로 인정한다.
- 유사 후보는 펀드 동일성 확정이나 계좌 적격성 증명으로 사용하지 않는다.

## 환헤지 원칙

- 상품명 `(H)`, `환헤지`, 지수명 `Currency Hedged`는 `hedged`다.
- 국내자산은 `not_applicable`이다.
- 해외 단일지역 상품에 헤지 표지가 없으면 `unhedged`로 추론하고 경고한다.
- TDF·글로벌 혼합자산은 내부 부분헤지 가능성이 있어 명시 근거가 없으면 `unknown`이다.
- `unknown`인 상품만 운용사 투자설명서·상품공시를 조회한다. 공시가 환노출·환헤지 미실시를 명시하면 `unhedged/high`, 환헤지를 명시하면 `hedged/high`로 오버라이드하고 공시 URL과 검증일을 저장한다.

## 액티브 검증 원칙

- 한투 ETF 구분이 `Active`이거나 KRX 공식 종목명에 `액티브`가 있으면 직접 근거로 확정한다.
- 한투 분류와 KRX 종목명이 모두 명확하지 않을 때만 금투협·운용사 공시를 조회한다.
- `실물복제`·`합성복제` 표시는 패시브의 직접 근거로 사용하며, 단순 `ETF`이면서 액티브 표지가 없을 때만 패시브 추론 경고를 남긴다.

## 실행

```powershell
uv --cache-dir .uv-cache run python -m backend.app.etf_classification_report --as-of 2026-07-15
```

결과는 `data/cache/classification/etf_asset_classification_YYYY-MM-DD.json`에 저장한다.
