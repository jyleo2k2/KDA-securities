# 연금계좌 ETF 적격성 계약

> 기준일: 시장·자산군 2026-07-15 / 한국투자증권 퇴직연금 상품목록 2026-06-30

## 목적

현재 상장되고 관측이 충분한 KRX ETF 945개 중 DC형·IRP·연금저축펀드에서 투자 가능한 상품만 계좌별로 분리한다. 자산군 분류와 계좌 적격성은 서로 다른 필드로 관리한다.

945개 전체 자산군 파일은 수집·분류 감사와 계좌 적격성 생성의 상위 입력일 뿐이다. 연금 운용 알고리즘은 이 파일을 직접 읽지 않고 `algorithm_input=true`, `product_scope=account_eligible_only`인 계좌별 파일만 읽는다.

## 판정 원칙

| 계좌 | 판정 기준 | 저장 상태 |
|---|---|---|
| DC형 | 레버리지·인버스 공통 차단 후 한국투자증권 공식 퇴직연금 매매가능 ETF 목록과 종목코드 정확 일치 | `eligible_at_kis` |
| IRP | DC형과 같은 공통 차단 규칙과 한투 공식 목록을 사용 | `eligible_at_kis` |
| 연금저축펀드 | 국내 상장 ETF 중 레버리지·인버스를 제외 | `eligible_by_account_rule` |

연금저축펀드 판정은 법·계좌 규칙에 따른 후보 분류다. 증권사 주문 시스템의 실제 취급 목록을 직접 확인한 값은 아니므로 `account_rule_not_provider_inventory`를 함께 저장한다.

## DC·IRP 투자한도

한투 공식 엑셀의 `퇴직연금 투자한도`를 그대로 사용한다.

- 70%: `general_risky_70_cap`
- 100%: `full_allocation_eligible`

`full_allocation_eligible`는 원리금보장이라는 뜻이 아니다. ETF는 투자손실이 발생할 수 있으므로 기존 엔진의 `capital_preservation`과 혼합하지 않는다.

## 제외 규칙

- 레버리지·인버스 ETF는 사업자 목록 포함 여부보다 먼저 세 계좌에서 강제 제외한다.
- DC·IRP 제외 사유는 `RETIREMENT_LEVERAGE_INVERSE_PROHIBITED`, 연금저축펀드는 `PENSION_SAVINGS_LEVERAGE_INVERSE_PROHIBITED`로 별도 저장한다.
- DC·IRP는 한투 공식 목록에 없는 선물·파생형 및 사업자 미취급 상품을 제외한다.
- 해외거래소 상장 ETF와 개별주식은 현재 KRX 국내 ETF 유니버스에 애초에 포함하지 않는다.
- 상장폐지 상품과 관측 부족 상품은 상위 KRX 유니버스 단계에서 제외한다.

## 공식 근거

- 한국투자증권 퇴직연금 매매가능 ETF/상장REITs 리스트: https://www.truefriend.com/pension/nwEtcinfo/Notice.jsp?cmd=A_NW_33030View&num=47065&subFlag=1
- 한국투자증권 퇴직연금 거래제한(레버리지·인버스·파생형 ETF 매매불가): https://www.truefriend.com/pension/nwEtcinfo/Notice.jsp?cmd=A_NW_33030View&num=46862&subFlag=1
- 퇴직연금감독규정: https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000212803
- 한국투자증권 연금저축 안내(레버리지·인버스 ETF 불가): https://truefriend.com/pension/nwInvestment/PersonalPensionGuid.jsp

## 실행

```powershell
uv run python -m backend.app.pension_eligible_etf_report `
  --as-of 2026-07-15 `
  --eligibility-as-of 2026-06-30
```

생성 파일은 `data/cache/classification/` 아래의 통합 적격 마스터와 DC·IRP·연금저축펀드 계좌별 JSON이다.

## 알고리즘 입력 경계

| 계좌 | 알고리즘 입력 파일 | 상품 수(2026-07-15) |
|---|---|---:|
| DC형 | `dc_eligible_etfs_2026-07-15.json` | 823 |
| IRP | `irp_eligible_etfs_2026-07-15.json` | 823 |
| 연금저축펀드 | `pension_savings_eligible_etfs_2026-07-15.json` | 861 |

- `etf_asset_classification_2026-07-15.json` 945개 파일: 알고리즘 입력 금지
- `pension_account_eligible_etfs_2026-07-15.json` 861개 합집합: 교차계좌 감사용이며 단일 계좌 알고리즘 입력 금지
- `PensionAccountUniverse.from_path(...)`는 계좌별 파일·계좌 일치·적격 상태·중복·레버리지·인버스 부재를 검증하고 조건을 어기면 로딩을 거부한다.
