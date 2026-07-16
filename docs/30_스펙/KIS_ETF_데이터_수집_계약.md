# 한국투자증권 ETF 데이터 수집 계약

## 목적

KRX 일별 시장 데이터로 만든 현재 상장·관측충분 ETF 목록을 입력으로 사용해, 한국투자증권 Open Trading API에서 ETF 구성종목과 현재가·NAV 관련 필드를 수집한다. 이 데이터는 ETF 중복도 분석과 상품 설명을 위한 보조 근거이며 매수 가능 여부나 미래수익률을 확정하지 않는다.

## 공식 API

- 인증: `POST /oauth2/tokenP`
- ETF 구성종목시세: `GET /uapi/etfetn/v1/quotations/inquire-component-stock-price`, TR ID `FHKST121600C0`
- ETF/ETN 현재가: `GET /uapi/etfetn/v1/quotations/inquire-price`, TR ID `FHPST02400000`
- 공식 예제: <https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/etfetn/etfetn_functions.py>

자격증명은 루트 `.env`의 `KIS_APP_KEY`, `KIS_APP_SECRET`에서만 읽는다. 로그·예외·원본·캐시·매니페스트에는 키와 액세스 토큰을 기록하지 않는다.

## 입력과 대상 범위

기본 입력은 `data/cache/krx/etf_market_evidence_YYYY-MM-DD.json` 중 최신 파일이다. 따라서 KRX 보고서에서 이미 제외한 상장폐지 종목과 253개 거래 관측 미만 종목은 한투 API 수집 대상에도 포함되지 않는다.

## 저장 구조

```text
data/raw/kis/
  components/YYYY-MM-DD/종목코드.json
  price/YYYY-MM-DD/종목코드.json
  manifests/etf_snapshot_YYYY-MM-DD.json
data/cache/kis/
  etf_snapshot_YYYY-MM-DD.json
```

원본 응답 bytes를 ETF·엔드포인트별로 저장하고 SHA-256을 매니페스트에 기록한다. 기존 원본이 정상인 경우 재호출하지 않으며 `--force`에서만 다시 수집한다. 정규화 캐시는 KRX 종목코드·상품명, 구성종목 요약, 구성종목 배열, 현재가 응답, 경고를 묶는다.

## 한계와 후속 소스

- 구성종목 배열이 빈 응답이면 그대로 보존하고 중복도 계산 대상에서 제외한다.
- 공개 시세 응답만으로 연금저축·IRP·DC 매수 가능 여부나 위험자산 분류를 확정할 수 없다. 금융회사 상품 마스터 또는 계좌별 주문가능상품 API의 별도 검증이 필요하다.
- 총보수·실부담비용과 분배금 이력은 운용사 공시, 금융투자협회·거래소 공시 등 별도 검증 소스가 필요하다.
- KRX에 이미 NAV와 장기 일별 시계열이 있으므로 동일 목적의 한투 NAV 일별 API를 전체 종목에 중복 호출하지 않는다.

## 실행

```powershell
uv --cache-dir .uv-cache run python -m backend.app.ingestion.kis --limit 5
uv --cache-dir .uv-cache run python -m backend.app.ingestion.kis
```
