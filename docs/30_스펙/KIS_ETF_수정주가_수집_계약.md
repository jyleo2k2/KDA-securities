# KIS ETF 수정주가 수집 계약

> 기준일: 2026-07-16  
> 용도: 연금계좌 적격 ETF의 기업행위 조정 가격수익률·변동성·상관관계 근거

## API와 고정 파라미터

- API: 국내주식기간별시세(일/주/월/년)
- Endpoint: `inquire-daily-itemchartprice`
- TR ID: `FHKST03010100`
- 시장: `FID_COND_MRKT_DIV_CODE=J`
- 주기: `FID_PERIOD_DIV_CODE=D`
- 가격: **`FID_ORG_ADJ_PRC=0` 수정주가**
- 한 번의 호출: 최대 100거래일, 최신일에서 과거일 순

`FID_ORG_ADJ_PRC=1` 원주가 요청은 이 파이프라인에서 허용하지 않는다. 모든 원본
페이지와 상품별 캐시에 사용 파라미터, SHA-256, 요청 종료일을 저장한다.

## 대상과 저장

KRX 전체 ETF가 아니라 `pension_account_eligible_etfs_YYYY-MM-DD.json`의
연금저축·IRP·DC 중 하나 이상 적격인 ETF만 수집한다.

```text
data/raw/kis/adjusted_daily_itemchartprice/{종목코드}/{요청종료일}.json
data/raw/kis/manifests/adjusted_prices_YYYYMMDD_YYYYMMDD.json
data/cache/kis/adjusted_prices/{기준일}/{종목코드}.json
data/cache/kis/adjusted_price_master_{기준일}.json
```

## 데이터 역할

- 한투 수정종가: 기업행위가 반영된 가격수익률·변동성·ETF 간 상관관계의 우선 입력
- KRX 종가·NAV: 거래소 원본 대조, 상장 상태, 괴리율·추적오차 근거
- KIND 분배금: 현금 분배를 포함하는 총수익률 계산 근거

한투의 `수정주가`를 현금 분배금까지 포함하는 총수익지수로 간주하지 않는다.
따라서 기존 KIND 분배금 이벤트를 제거하거나 한투 수정종가에 자동 합산하지 않는다.
수정주가와 분배금의 중복 여부를 기업행위 유형별로 검증하기 전에는 두 결과를
`price_return`과 `distribution_adjusted_total_return`으로 구분한다.

## 실행

```powershell
uv --cache-dir .uv-cache run python -m backend.app.ingestion.kis_adjusted_prices \
  --from-date 2020-01-02 --to-date 2026-07-15 --delay-seconds 0.12 --workers 4
```

## 2026-07-16 수집·결합 결과

- 대상: 연금계좌 적격 ETF 861개
- 기간: 2020-01-02~2026-07-15
- 수정주가 관측: 897,330개
- 수집 실패: 0개
- 시장근거 보고서 적용: 861개 전부
- 교육용 포트폴리오 위험·상관관계 적용: 계좌별 유니버스 누적 2,507개 및 최종 후보
  720개 전부
- KRX 종가 fallback: 비연금 대상 84개

응답의 `mod_yn=Y` 관측은 0건이었다. 이것을 수정주가 미적용으로 해석하지 않고,
요청 계약의 `FID_ORG_ADJ_PRC=0`과 원본 응답을 근거로 사용한다. 기업행위 발생 여부를
판정할 때는 별도 기업행위 공시와 대조한다.

`prtt_rate`는 정상 관측에도 0이 아닌 값이 존재하므로 단독으로 분할·병합 신호로
사용하지 않는다. 종목 이벤트 마스터는 `mod_yn=Y` 또는 `revl_issu_reas`가 명시된
관측만 후보로 만들고, 사유에 분할·병합·합병이 직접 기재된 경우에만 해당 유형으로
확정한다. 현재 897,330개 관측에서 `mod_yn=Y`와 명시 사유가 모두 0건이므로 한투 기반
분할·병합 이벤트도 0건이다.
