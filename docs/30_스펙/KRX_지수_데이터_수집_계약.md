# KRX 주식·채권 지수 데이터 수집 계약

> 기준일: 2026-07-16  
> 용도: 연금 포트폴리오의 국내 주식·채권 위험, 상관관계, 스트레스 근거

## 승인 API

| 서비스 | API ID | 포트폴리오 사용 |
|---|---|---|
| KRX 시리즈 일별시세정보 | `krx_dd_trd` | KRX 300 |
| KOSPI 시리즈 일별시세정보 | `kospi_dd_trd` | 코스피, 코스피 200 |
| KOSDAQ 시리즈 일별시세정보 | `kosdaq_dd_trd` | 코스닥, 코스닥 150 |
| 채권지수 시세정보 | `bon_dd_trd` | KRX 채권지수, KTB 지수, 국고채프라임지수 |

모든 요청은 `basDd=YYYYMMDD`와 서버 전용 `AUTH_KEY` 헤더를 사용한다. 키는
`.env`의 기존 `KRX_API_KEY`만 사용하며 로그·원본·매니페스트에 기록하지 않는다.

## 저장 구조

```text
data/raw/krx/indices/{krx|kospi|kosdaq|bond}/YYYY/MM/YYYYMMDD.json
data/raw/krx/manifests/index_daily_all_YYYYMMDD_YYYYMMDD.json
data/cache/krx/index_benchmark_history_YYYYMMDD_YYYYMMDD.json
```

원본에는 API가 반환한 모든 업종·규모 지수를 보존한다. 알고리즘 캐시는 대표지수
8개만 포함해, 업종지수를 임의로 자산군 대표값으로 사용하는 오류를 막는다.

## 수익률 기준

- 주식지수: `CLSPRC_IDX` 종가지수의 일별 변화율
- 채권지수: 이자수익을 포함하는 `TOT_EARNG_IDX` 총수익지수의 일별 변화율
- 채권 보조정보: 순가격지수, 시장가격지수, 평균수익률, 듀레이션, 컨벡서티

주식 가격지수와 채권 총수익지수의 정의가 다르다는 사실을 출력 메타데이터에
`return_basis`로 명시한다. 이 자료는 역사적 변동성·상관관계·스트레스 근거이며
미래 기대수익률이나 ETF 계좌 적격성의 직접 입력이 아니다.

## 실행

```powershell
uv --cache-dir .uv-cache run python -m backend.app.ingestion.krx_indices \
  --from-date 2020-01-02 --to-date 2026-07-15 --workers 8
```

## 2026-07-16 수집 결과

- 조회기간: 2020-01-02~2026-07-15
- 평일: 1,705일
- 날짜·서비스 요청: 6,820건
- 실패: 0건
- 원본 행: 206,525행
- 계산 가능 행: 203,115행
- 주식 대표지수 5종: 각 1,604개 실제 거래 관측
- KTB·국고채프라임: 각 1,604개 관측
- KRX 채권지수: 1,705개 평일 관측

주식과 KTB·국고채프라임의 관측일을 기준으로 교집합을 만든 뒤 일별 수익률과
상관관계를 계산한다. KRX 채권지수가 주식시장 휴장일에도 값을 제공하는 경우가 있어
단순 행 위치 결합이나 결측값의 0% 수익률 대체는 금지한다.
