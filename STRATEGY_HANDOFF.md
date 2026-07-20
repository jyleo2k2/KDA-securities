# 전략 엔진 감사 핸드오프

작성일: 2026-07-20  
상태: 코드 변경 전 감사 완료. 아래 P0부터 구현할 수 있음.

## 목적

연금 전략 기능은 하나의 엔진이 아니라 아래 경로가 결합된 구조다.

```text
투자성향 5단계
  └─ educational_portfolio.PROFILE_POLICY (전략 ID 5개)
       ├─ 교육용 포트폴리오: 동적 5-슬리브 배분 + ETF 후보선정
       └─ 연금계산기: 연령별 성장/안정/현금 3자산 매트릭스

ETF 분류 전략 코드 ──> 교육용 포트폴리오의 슬리브 배정
뉴스/테마 분류 ──────> 관찰용 이벤트 가이드 (매매·비중 결정 아님)
```

고정 전략 ID는 다음 다섯 가지다.

| ID | 성향 |
|---|---|
| `capital_preservation_core` | 안정형 |
| `defensive_diversified_core` | 안정추구형 |
| `balanced_core_satellite` | 위험중립형 |
| `growth_core_satellite` | 적극투자형 |
| `barbell_growth_tactical` | 공격투자형 |

## 먼저 읽을 파일

1. `AGENTS.md` 및 `docs/team/_공통_AI규칙.md`
2. `backend/app/engine/AGENTS.md` (엔진 소유·불변조건)
3. `backend/app/engine/educational_portfolio.py`
4. `backend/app/engine/pension_calculator.py`
5. `backend/app/engine/assumptions.py`
6. `backend/app/engine/asset_classification.py`
7. `tests/test_educational_portfolio.py`, `tests/test_pension_calculator.py`

엔진 변경은 순수 함수로 유지한다. DB 재적재·마이그레이션·원격 DB 작업은 이 작업 범위가 아니다.

## P0 — 성향 밖 `strategy_id` 직접 선택 차단

### 현행 문제

`PensionCalculatorInput.strategy_id`는 알려진 전략 ID인지 만 확인한다.
`calculate_pension()`은 `strategy_id`가 있으면 입력 `risk_profile`보다 우선해 해당 전략으로 적립·수령액을 계산한다.

- 검증: `backend/app/engine/models.py`의 `PensionCalculatorInput.validate_calculation_scope`
- 선택: `backend/app/engine/pension_calculator.py`의 `calculate_pension`

따라서 안정형 사용자가 `barbell_growth_tactical`을 직접 넘기면 공격형 가정으로 계산된다.

### 재현

```powershell
uv run python -c "from decimal import Decimal; from backend.app.engine.models import AccountType,RiskProfile,PensionCalculatorInput; from backend.app.engine.pension_calculator import calculate_pension; base=dict(current_age=25,contribution_end_age=60,monthly_contribution_krw=Decimal('100000'),current_balance_krw=Decimal('0'),account_type=AccountType.PENSION_SAVINGS,risk_profile=RiskProfile.STABLE); low=calculate_pension(PensionCalculatorInput(**base)); high=calculate_pension(PensionCalculatorInput(**(base|{'strategy_id':'barbell_growth_tactical'}))); print(low.headline.total_krw, high.headline.total_krw)"
```

감사 시 결과: `71016373 120230725`.

### 권장 수정

- `strategy_id`가 제공되면 그 전략의 프로필 순위가 `risk_profile` 이하인지 검증한다.
- 범위 밖이면 `ValueError`/Pydantic validation error로 거절한다. 자동 하향 조정은 사용자가 선택한 전략을 숨길 수 있으므로 권장하지 않는다.
- 계산 결과에 실제 선택 프로필 또는 `selected_strategy_id`를 명시하는 것도 검토한다.

### 수용 기준

- 안정형 + 공격 전략 ID 입력은 422 또는 명확한 validation error.
- 동일·낮은 위험 전략 ID는 통과.
- 기존 `default_visible` 규칙은 유지.
- `uv run pytest -q tests/test_pension_calculator.py` 통과.

## P0 — 연금저축 공격형 전략 목록과 실제 계산 배분 일치

### 현행 문제

`PENSION_SAVINGS_EXTENSION`은 20대/30대 공격형을 각각 90/10/0, 80/20/0으로 확장한다.

- 실제 적립 경로 `_accumulate()` → `_allocation()`은 확장값을 사용한다.
- 전략 목록 `_build_strategies()`는 `ALLOCATION_MATRIX`를 직접 읽어 확장값을 누락한다.

### 재현

```powershell
uv run python -c "from decimal import Decimal; from backend.app.engine.models import AccountType,RiskProfile,PensionCalculatorInput; from backend.app.engine.pension_calculator import calculate_pension,_allocation; x=PensionCalculatorInput(current_age=25,contribution_end_age=60,monthly_contribution_krw=Decimal('100000'),current_balance_krw=Decimal('0'),account_type=AccountType.PENSION_SAVINGS,risk_profile=RiskProfile.AGGRESSIVE); r=calculate_pension(x); s=next(v for v in r.strategies if v.strategy_id=='barbell_growth_tactical'); print('listed',s.growth_percent,s.safe_percent,s.cash_percent); w=_allocation(account_type=AccountType.PENSION_SAVINGS,age=25,profile=RiskProfile.AGGRESSIVE); print('actual',w.growth_percent,w.safe_percent,w.cash_percent)"
```

감사 시 결과: 목록 `70 30 0`, 실제 계산 `90 10 0`.

### 권장 수정

`_build_strategies()`에서 직접 매트릭스를 읽지 말고 `_allocation(account_type=inputs.account_type, age=inputs.current_age, profile=profile)`을 사용한다.

### 수용 기준

- 25세·연금저축·공격형 전략 목록이 90/10/0.
- 35세·연금저축·공격형 전략 목록이 80/20/0.
- DC/IRP 전략 목록은 성장자산 70% 이하.
- 화면에 보이는 전략 비중과 적립 계산 첫 연령대 비중이 일치.

## P0 — 적격 TDF의 교육용 포트폴리오 연결 결정

### 현행 문제

`classify_etf()`는 TDF를 `asset_class='multi_asset'`, `strategy='target_date'`로 분류한다. 그러나 `_product_sleeve()`는 `multi_asset` 분기가 없어 `None`을 반환한다.

결과적으로 TDF는 교육용 포트폴리오 후보선정과 보유 ETF 리밸런싱 집계에서 제외된다. 적격 TDF 법정 예외를 사용하려는 정책과 연결되지 않은 상태다.

### 재현

```powershell
uv run python -c "from backend.app.engine.asset_classification import EtfClassificationInput,classify_etf; from backend.app.engine.educational_portfolio import _product_sleeve; c=classify_etf(EtfClassificationInput(isu_code='000000',isu_name='TDF2045',benchmark_name='',kis_index_name='',kis_industry_name='')); print(c['asset_class'],c['strategy']); print(_product_sleeve({'classification':c}))"
```

감사 시 결과: `multi_asset target_date`, `None`.

### 결정 필요

엔진 소유자와 다음 중 하나를 확정해야 한다.

1. TDF를 단일 `multi_asset` 슬리브로 추가하고, 적격 여부·글라이드패스·법정 예외를 별도 표현한다.
2. TDF를 교육용 후보에서 의도적으로 제외하되, 보유자산/응답에 명시적 제외 사유를 노출한다.
3. TDF 내부 자산배분을 분해해 기존 슬리브로 환산한다. 데이터 근거와 계산 정책이 추가로 필요해 가장 큰 작업이다.

계좌별 위험자산 규칙을 임의로 우회하면 안 된다.

## P1 — 전략 표시 계약 정리

### 현행 문제

서버 `EducationalPortfolioEvaluation`에는 `strategy_presentation`이 있으나 `frontend/src/api/types.ts`의 동명 타입에는 없다. `PortfolioHoldingsPanel`은 `strategy_label`을 그대로 표시한다. 서버의 `strategy_label`은 내부 ID다.

또한 표시명은 다음처럼 불일치한다.

- `strategy_presentation.py`: 공격형 `테마 집중 전략`
- `chat/service.py`: 공격형 `바벨형 성장·전술 전략`
- 포트폴리오 패널: 내부 ID를 출력할 가능성

### 권장 수정

- 프론트 타입에 `strategy_presentation`을 추가한다.
- 화면은 `strategy_presentation.display_name`과 `summary`를 사용한다.
- 챗봇의 `_STRATEGY_LABELS`는 presentation SSOT를 사용하거나 표현을 의도적으로 통일한다.
- 서버의 `asset_class_allocation`도 프론트 타입과 필요 시 화면에 연결한다.

## P1 — ETF 테마의 `default_sleeve` 의미 정리

`data/reference/etf_theme_catalog.json`의 23개 테마에는 `default_sleeve`가 있으나, 런타임 코드는 이를 읽어 배분에 사용하지 않는다. 실제 슬리브는 상품의 ETF 분류 결과 `_product_sleeve()`로 결정된다.

둘 중 하나로 정리한다.

- `default_sleeve`를 설명용 메타데이터라고 명시한다.
- 또는 분류 결과와 충돌 시의 우선순위를 설계하고 실제 선택 로직에 사용한다.

## 별도 기능 상태

`backend/app/engine/strategy.py`에는 다음이 구현돼 있으나 API·챗봇·프론트 연결은 없다.

- 현금흐름을 제거한 TWR/변동성/MDD
- CPPI 유사 위험예산
- 전술 슬리브 5%p 초과 또는 10% 수익 시 이익실현 규칙

제품 기능으로 공개할지, 실험용 엔진으로 유지할지 결정 필요.

## 변경 시 지켜야 할 불변조건

- DC/IRP 일반 위험자산 70% 한도와 적격 TDF/디폴트옵션 예외를 혼동하지 않는다.
- 연금저축에 DC/IRP 70% 한도를 적용하지 않는다.
- 후보 ETF 순위에 과거 수익률을 쓰지 않는다.
- 계획수익률(CMA 기반 교육 가정)을 미래수익 예측으로 표현하지 않는다.
- 리밸런싱은 추가 납입 우선이며 매도 주문을 생성하지 않는다.
- 엔진은 DB·네트워크·LLM 없이 입력 기반 순수 함수로 유지한다.

## 검증 명령

```powershell
uv run pytest -q tests/test_asset_classification.py tests/test_strategy.py tests/test_educational_portfolio.py tests/test_pension_calculator.py tests/test_planning_return.py tests/test_portfolio_risk_and_cma.py tests/test_chat_live_news.py
uv run pytest -q
```

감사 시 첫 번째 전략 관련 테스트 묶음은 `66 passed`였다.

## 감사에서 확인한 주요 코드 위치

- 전략 정책/슬리브/후보/리밸런싱: `backend/app/engine/educational_portfolio.py`
- 전략 ID 표시 메타데이터: `backend/app/engine/strategy_presentation.py`
- 연령별 가정 매트릭스: `backend/app/engine/assumptions.py`
- 연금계산기: `backend/app/engine/pension_calculator.py`
- ETF 분류 전략 코드: `backend/app/engine/asset_classification.py`
- 테마 후보: `backend/app/engine/etf_theme.py`
- 뉴스 이벤트 가이드: `backend/app/chat/news_event_strategy.py`
- 챗봇 전략 설명: `backend/app/chat/service.py`
- 프론트 포트폴리오 표시: `frontend/src/components/PortfolioHoldingsPanel.tsx`
