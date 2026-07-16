# KRX ETF 데이터 수집·과거 시장근거 계약

> 목적: 통합연금포털의 분기 공시를 KRX ETF 일별 통계로 보완한다. 이 데이터는 과거 실적 근거이며 미래 수익률 예측이나 계좌 적격성 확정에 사용하지 않는다.

## 1. 사용 API

- API: `ETF 일별매매정보`
- API ID: `etf_bydd_trd`
- Endpoint: `https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd`
- 요청: `basDd=YYYYMMDD`, 헤더 `AUTH_KEY`
- 공식 명세: <https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES003_S2.cmd?BO_ID=nrEpCLaZpoLCTzPUMxuF>

키는 루트 `.env`의 `KRX_API_KEY`로만 주입한다. 로그·예외·원본·매니페스트에 키를 기록하지 않는다.

## 2. 원본 보존

```text
data/raw/krx/
  etf_bydd_trd/YYYY/MM/YYYYMMDD.json
  manifests/etf_bydd_trd_YYYYMMDD_YYYYMMDD.json
```

- 응답 bytes를 수정하지 않고 날짜별 JSON으로 보존한다.
- 저장은 임시 파일 작성 후 원자적으로 교체한다.
- 기존 파일은 스키마·기준일을 검증한 후 재호출하지 않는다.
- 매니페스트에는 기준일, 상태, 수신 행, 계산 가능 행, SHA-256, 상대경로, 수집시각을 남긴다.
- `data/raw/`와 `data/cache/`는 Git에 커밋하지 않는다.

## 3. 필드 계약

원본 19개 필드를 모두 검증한다.

```text
BAS_DD, ISU_CD, ISU_NM, TDD_CLSPRC, CMPPREVDD_PRC, FLUC_RT,
NAV, TDD_OPNPRC, TDD_HGPRC, TDD_LWPRC, ACC_TRDVOL, ACC_TRDVAL,
MKTCAP, INVSTASST_NETASST_TOTAMT, LIST_SHRS, IDX_IND_NM,
OBJ_STKPRC_IDX, CMPPREVDD_IDX, FLUC_RT_IDX
```

KRX는 평일 휴장일에도 ETF 목록을 반환할 수 있으며 이때 가격 필드는 빈 문자열이다. 따라서 `row_count`는 수신 행, `usable_row_count`는 `TDD_CLSPRC`가 있는 계산 가능 행으로 분리한다. 휴장일을 0행 응답으로 가정하지 않는다.

## 4. 과거 시장근거 엔진

ETF별 최근 253개 실제 거래 관측으로 다음을 계산한다. 현재 상장되어 있어도 253개 관측이 없거나 보고일 종가가 없는 상품은 운용 후보에서 제외한다.

가격 입력은 연금계좌 적격 ETF에 한해 한투
`inquire-daily-itemchartprice`의 `FID_ORG_ADJ_PRC=0` 수정종가를 우선한다. KRX는
NAV·거래대금·순자산·기초지수와 현재 상장 여부를 제공한다. 한투 수정주가가 없는
비연금 비교상품만 KRX 종가로 fallback하며, 상품별 출처와 경고를 결과에 저장한다.

| 지표 | 정의 |
|---|---|
| 3·6·12개월 과거수익률 | 종가의 63·126·252 거래구간 변화율 |
| 연환산 변동성 | 일별 종가수익률 표본표준편차 × `sqrt(252)` |
| 최대낙폭 | 관측구간 고점 대비 최대 하락률 |
| 유동성 | 일별 거래대금 중앙값 |
| 규모 | 순자산총액 중앙값 |
| 가격-NAV 괴리 | `abs(종가 / NAV - 1)` 중앙값 |
| 추적오차 대용치 | NAV수익률-기초지수수익률의 연환산 표본표준편차 |

출력 파일은 `data/cache/krx/etf_market_evidence_YYYY-MM-DD.json`이다. 상품 목록에는 보고일 KRX 상장 목록에 포함되고 253개 관측과 보고일 종가가 모두 있는 ETF만 싣는다. 상장폐지 상품과 관측 부족 상품의 개별 항목은 제외하고 제외 건수만 기록한다. 원본은 감사·재현을 위해 수정하지 않는다.

## 5. 사용 금지·추가 데이터

- 과거수익률을 미래 기대수익률로 변환하지 않는다.
- 기초지수명이 같은 상품끼리도 총보수·분배금·복제방식이 없으면 최종 순위를 만들지 않는다.
- ETF 이름의 `레버리지`·`인버스` 패턴은 격리 신호일 뿐 계좌 적격성 증명이 아니다.
- 계좌별 매수 가능 여부, DC·IRP 위험자산 분류, 법정 예외는 금융회사·공식 상품 마스터로 별도 검증한다.
- 총보수·실부담비용·분배금 포함 총수익률은 KRX 일별 API 밖의 데이터다.

## 6. 재현 명령

```powershell
uv --cache-dir .uv-cache run python -m backend.app.ingestion.krx --from-date 2020-01-02 --to-date 2026-07-14 --workers 8
uv --cache-dir .uv-cache run python -m backend.app.market_evidence_report
```

2026-07-15 검증 스냅샷: 평일 파일 1,704개, 휴장 101일, 수신 1,229,897행,
계산 가능 1,154,131행, 수집 실패 0건. 2026-07-16 재생성한 시장근거 945개 중
연금계좌 적격 861개는 한투 수정종가, 비연금 비교상품 84개는 KRX 종가를 사용했다.
