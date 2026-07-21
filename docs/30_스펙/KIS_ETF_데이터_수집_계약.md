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

원격 서비스의 구성종목 답변은 로컬 캐시가 아니라 `etf_component_snapshots`와 `etf_component_snapshot_items`의 최신 성공 스냅샷을 사용한다. 주간 적재기는 최신 `ready` ETF 유니버스의 고유 `isu_code`를 대상으로 KIS 원문·SHA-256·수집시각을 보존하고, 비중 상위 3개만 조회용 행으로 정규화한다. 테마 문서에 비중을 복사하지 않으며, 응답 시 ETF 종목코드와 구성종목 행의 `stck_shrn_iscd`, `hts_kor_isnm`, `etf_cnfg_issu_rlim`, 수집시각을 함께 연결한다. 상세 가드레일은 [ETF 테마 챗봇 계약](./ETF_테마_챗봇_계약.md)을 따른다.

KIS가 정상 응답 코드(`rt_cd=0`)를 주더라도 `output1.etf_cnfg_issu_cnt`가 1 이상인데 `output2`가 빈 경우는 정상적인 무구성 상품이 아니라 **임시 상세 누락**으로 판정한다. 이 경우 지수 백오프로 최대 3회 재시도한다. 재시도 후에도 비어 있으면 원문은 `empty` 스냅샷으로 보존하되 수집 run을 `partial`로 표시하고 실행을 실패 코드로 종료하며, `--resume-today`의 재수집 대상에 다시 포함한다. 명시된 구성종목 수가 0인 경우만 정상 빈 응답으로 확정한다.

서비스 조회기는 가장 최근 기록을 무조건 선택하지 않는다. `status='succeeded'`이고 `component_count > 0`인 마지막 정상 스냅샷만 사용해, 후속 임시 빈 응답이 이미 확보한 정상 TOP3를 가리지 않도록 한다. 상세 행은 있는데 필수 이름·비중을 하나도 정규화하지 못한 응답도 성공 처리하지 않는다.

## 한계와 후속 소스

- 임시 상세 누락은 재시도·재개 대상으로 유지한다. 반복 수집 뒤에도 KIS 상세가 확보되지 않은 상품은 공식 KRX PDF(Portfolio Deposit File) 또는 운용사 공시를 보조 소스로 검토하되, 출처와 기준일을 별도 저장하고 KIS 응답으로 위장하지 않는다.
- 공개 시세 응답만으로 연금저축·IRP·DC 매수 가능 여부나 위험자산 분류를 확정할 수 없다. 금융회사 상품 마스터 또는 계좌별 주문가능상품 API의 별도 검증이 필요하다.
- 총보수·실부담비용과 분배금 이력은 운용사 공시, 금융투자협회·거래소 공시 등 별도 검증 소스가 필요하다.
- KRX에 이미 NAV와 장기 일별 시계열이 있으므로 동일 목적의 한투 NAV 일별 API를 전체 종목에 중복 호출하지 않는다.

## 실행

```powershell
uv --cache-dir .uv-cache run python -m backend.app.ingestion.kis --limit 5
uv --cache-dir .uv-cache run python -m backend.app.ingestion.kis
uv run python -m backend.app.ingestion.kis_component_snapshots --resume-today
uv run python -m backend.app.ingestion.kis_component_snapshots --isu-code 449450
```

`--isu-code`는 여러 번 지정할 수 있으며 최신 `ready` ETF 유니버스 안의 해당 종목만 재수집한다. 운영 백필과 장애 종목 재검증에서 전체 861개를 불필요하게 다시 호출하지 않기 위한 옵션이다.
