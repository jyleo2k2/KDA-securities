import re
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..engine import AccountType
from ..etf_theme_repository import (
    EtfThemeRepository,
    get_default_etf_theme_repository,
)
from ..text_normalization import normalize_search_text
from .models import ChatIntent


class BlockedReason(StrEnum):
    SENSITIVE_INFORMATION = "sensitive_information"
    FUTURE_PREDICTION = "future_prediction"
    ORDER_REQUEST = "order_request"
    FOREIGN_MARKET_OR_INDIVIDUAL_STOCK = "foreign_market_or_individual_stock"
    PRODUCT_LEVEL_UNAVAILABLE = "product_level_unavailable"
    ACCOUNT_SELECTION_REQUIRED = "account_selection_required"
    UNSUPPORTED = "unsupported"


class NewsScopeNotice(StrEnum):
    COMPANY = "company"
    UNSUPPORTED_MARKET = "unsupported_market"
    PENSION = "pension"


class AccountRuleTopic(StrEnum):
    PENSION_ACCOUNT_OVERVIEW = "pension_account_overview"
    PENSION_RECEIPT_START = "pension_receipt_start"
    PENSION_RECEIPT_TAX = "pension_receipt_tax"
    PRIVATE_PENSION_THRESHOLD = "private_pension_threshold"
    NON_PENSION_WITHDRAWAL = "non_pension_withdrawal"


class ThemeContentTopic(StrEnum):
    OVERVIEW = "overview"
    REPRESENTATIVE_COMPANIES = "representative_companies"
    INVESTMENT_CONSIDERATIONS = "investment_considerations"
    PERFORMANCE_DRIVERS = "performance_drivers"
    RISKS = "risks"


class DistributionReinvestmentRequest(BaseModel):
    """Explicit chat inputs for an educational distribution-reinvestment guide."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    isu_code: str = Field(pattern=r"^[0-9A-Z]{6}$")
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    reinvestment_price_krw: Decimal = Field(gt=0, allow_inf_nan=False)
    as_of: date
    rebalance_on: date

    @model_validator(mode="after")
    def require_rebalance_on_or_after_as_of(self) -> "DistributionReinvestmentRequest":
        if self.rebalance_on < self.as_of:
            raise ValueError("rebalance_on must be on or after as_of")
        return self


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized_message: str = Field(min_length=1, max_length=1000)
    intent: ChatIntent
    account_types: tuple[AccountType, ...] = ()
    news_query: str | None = Field(default=None, min_length=1, max_length=200)
    requests_event_strategy: bool = False
    requests_live_news: bool = False
    news_scope_notice: NewsScopeNotice | None = None
    max_results: int = Field(default=3, ge=1, le=5)
    combines_account_rules: bool = False
    requests_tax_credit: bool = False
    requests_withdrawal_tax: bool = False
    requests_pension_planner: bool = False
    account_rule_topic: AccountRuleTopic | None = None
    theme_id: str | None = None
    theme_content_topic: ThemeContentTopic | None = None
    requests_theme_candidates: bool = False
    requests_theme_holdings: bool = False
    distribution_isu_code: str | None = None
    distribution_reinvestment: DistributionReinvestmentRequest | None = None
    glossary_term_id: str | None = None
    blocked_reason: BlockedReason | None = None

    @model_validator(mode="after")
    def verify_intent_fields(self) -> "QueryPlan":
        if self.intent == ChatIntent.NEWS and self.news_query is None:
            raise ValueError("news intent requires news_query")
        if self.intent == ChatIntent.GLOSSARY and self.glossary_term_id is None:
            raise ValueError("glossary intent requires glossary_term_id")
        if self.intent != ChatIntent.GLOSSARY and self.glossary_term_id is not None:
            raise ValueError("glossary_term_id is only valid for glossary intent")
        if self.intent != ChatIntent.NEWS and self.news_query is not None:
            raise ValueError("news_query is only valid for news intent")
        if self.intent != ChatIntent.NEWS and self.requests_event_strategy:
            raise ValueError("event strategy requires news intent")
        if self.intent != ChatIntent.NEWS and self.requests_live_news:
            raise ValueError("live news requires news intent")
        if self.intent != ChatIntent.NEWS and self.news_scope_notice is not None:
            raise ValueError("news scope notice requires news intent")
        if self.intent == ChatIntent.OUT_OF_SCOPE and self.blocked_reason is None:
            raise ValueError("out_of_scope intent requires blocked_reason")
        if self.intent != ChatIntent.OUT_OF_SCOPE and self.blocked_reason is not None:
            raise ValueError("blocked_reason is only valid for out_of_scope")
        requests_pension_tax = self.requests_tax_credit or self.requests_withdrawal_tax
        if self.intent == ChatIntent.PENSION_TAX and not requests_pension_tax:
            raise ValueError("pension_tax intent requires a requested calculation")
        if self.intent != ChatIntent.PENSION_TAX and requests_pension_tax:
            raise ValueError("pension tax flags require pension_tax intent")
        if (
            self.intent != ChatIntent.ACCOUNT_RULE
            and self.account_rule_topic is not None
        ):
            raise ValueError("account_rule_topic requires account_rule intent")
        if self.intent == ChatIntent.ETF_THEME and (
            self.theme_id is None or self.theme_content_topic is None
        ):
            raise ValueError("etf_theme intent requires theme fields")
        if self.intent != ChatIntent.ETF_THEME and (
            self.theme_id is not None
            or self.theme_content_topic is not None
            or self.requests_theme_candidates
            or self.requests_theme_holdings
        ):
            raise ValueError("theme fields require etf_theme intent")
        if self.intent != ChatIntent.ETF_DISTRIBUTION and (
            self.distribution_isu_code or self.distribution_reinvestment is not None
        ):
            raise ValueError("distribution fields require etf_distribution intent")
        return self


_RRN = re.compile(r"(?<!\d)\d{6}[ -]?[1-8]\d{6}(?!\d)")
_VALUE_BINDER = r"\s*(?:(?:은|는|이|가)\s*)?(?::|=)?\s*"
_ACCOUNT_LABEL = r"(?:계좌\s*번호|account\s*(?:number|no\.?))"
_ACCOUNT_VALUE = r"(?<!\d)\d(?:[ -]?\d){7,19}(?!\d)"
_PASSWORD_LABEL = r"(?:비밀\s*번호|패스\s*워드|password)"
_PASSWORD_VALUE = r"[A-Za-z0-9!@#$%^&*_.-]{4,64}"
_AUTH_CODE_LABEL = r"(?:O\s*T\s*P|보안\s*카드(?:\s*번호)?)"
_AUTH_CODE_VALUE = r"(?<!\d)\d(?:[ -]?\d){3,11}(?!\d)"
_PHONE = re.compile(r"(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)")
_EMAIL = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])",
    re.I,
)
_CARD_LABEL = r"(?:카드\s*(?:번호|no\.?)|card\s*(?:number|no\.?))"
_CARD_VALUE = r"(?<!\d)\d(?:[ -]?\d){14,18}(?!\d)"
_TOKEN_LABEL = r"(?:api\s*key|access\s*token|secret(?:\s*key)?|인증\s*키)"
_TOKEN_VALUE = r"(?:sk|sbp?|eyJ)[A-Za-z0-9_\-\.]{12,}"
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(_ACCOUNT_LABEL + _VALUE_BINDER + _ACCOUNT_VALUE, re.I),
    re.compile(_ACCOUNT_VALUE + _VALUE_BINDER + _ACCOUNT_LABEL, re.I),
    re.compile(_PASSWORD_LABEL + _VALUE_BINDER + _PASSWORD_VALUE, re.I),
    re.compile(_PASSWORD_VALUE + _VALUE_BINDER + _PASSWORD_LABEL, re.I),
    re.compile(_AUTH_CODE_LABEL + _VALUE_BINDER + _AUTH_CODE_VALUE, re.I),
    re.compile(_AUTH_CODE_VALUE + _VALUE_BINDER + _AUTH_CODE_LABEL, re.I),
    re.compile(_CARD_LABEL + _VALUE_BINDER + _CARD_VALUE, re.I),
    re.compile(_CARD_VALUE + _VALUE_BINDER + _CARD_LABEL, re.I),
    re.compile(_TOKEN_LABEL + _VALUE_BINDER + _TOKEN_VALUE, re.I),
    re.compile(_TOKEN_VALUE + _VALUE_BINDER + _TOKEN_LABEL, re.I),
)
_ORDER_REQUEST = re.compile(
    r"매수해|매도해|주문해|사\s*줘|팔아\s*줘|대신\s*사|대신\s*팔|자동\s*투자"
)
_FUTURE_PREDICTION = re.compile(
    r"(?:향후|내년|다음\s*분기).{0,15}(?:수익률|오를|내릴|예측|전망|보장)"
    r"|미래\s*(?:수익률|가격|주가|오를|내릴|예측|전망|보장)"
    r"|미래(?:의|에는?|를|는|은|가|이)\s+.{0,15}"
    r"(?:수익률|가격|주가|오를|내릴|예측|전망|보장)"
    r"|(?:수익률|가격).{0,15}(?:예측|보장|확정)|목표가"
)
_PRODUCT_LEVEL = re.compile(r"개별\s*상품|상품\s*추천|상품\s*비교|판매\s*중인\s*상품")
# 입문자는 "X가 뭐야" 형태로 용어부터 묻는다. 정의는 승인 문서의 고정
# 문장으로 답하므로 여기서는 어떤 용어인지만 식별한다.
_GLOSSARY_QUESTION = re.compile(
    r"뭐(?:야|예요|에요|지|니|냐)|무슨\s*(?:말|뜻)|무엇|"
    r"뜻이?\s*(?:뭐|무엇|어떻게)|어떤\s*(?:의미|뜻)|"
    r"쉽게\s*(?:알려|설명|말해)|설명해|알려\s*줘|모르겠|"
    r"안\s*(?:돼|되)|괜찮(?:아|을까)|해도\s*(?:돼|되)"
)
# 무엇을 물어야 할지 모르는 상태를 그대로 표현한 질문. 특정 기능으로
# 분류할 수 없지만 서비스의 첫 질문이 될 가능성이 높다.
_GETTING_STARTED_QUESTION = re.compile(
    r"(?:뭐|무엇|어디|어떻게|어디서)\s*(?:부터|서부터)|"
    r"처음(?:에는|엔|부터|인데|이라|이야|이면)?\s*(?:뭐|무엇|뭘|어떻게|어디)|"
    r"어떻게\s*시작|시작(?:하는\s*법|하려면|해야)|"
    r"뭘\s*(?:해야|하면)|무엇을\s*해야|"
    r"어떻게\s*하는\s*(?:건지|지)|감이?\s*안\s*(?:와|잡)"
)


def _is_getting_started_question(message: str) -> bool:
    """Detect "뭐부터 해야 할지 모르겠어" style openers."""

    return _GETTING_STARTED_QUESTION.search(message) is not None


_GLOSSARY_TERM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("risk_asset_cap", re.compile(r"위험\s*자산(?:\s*(?:한도|비중|70\s*%?))?")),
    ("safe_asset", re.compile(r"안전\s*자산")),
    ("default_option", re.compile(r"디폴트\s*옵션|사전지정\s*운용")),
    ("tdf", re.compile(r"TDF|타깃\s*데이트", re.I)),
    ("rebalancing", re.compile(r"리\s*밸런싱|리밸런스")),
    ("total_expense_ratio", re.compile(r"총\s*보수|보수율|운용\s*보수")),
    ("principal_guaranteed", re.compile(r"원리금\s*보장")),
    ("performance_based", re.compile(r"실적\s*배당")),
    ("tax_deferral", re.compile(r"과세\s*이연")),
    ("pension_income_tax", re.compile(r"연금\s*소득세")),
    ("in_kind_transfer", re.compile(r"실물\s*이전")),
    ("tax_credit", re.compile(r"세액\s*공제")),
    (
        "db_dc",
        re.compile(
            r"DB\s*형?\s*(?:이?랑|과|와|vs)?\s*DC\s*형?|확정\s*(?:급여|기여)",
            re.I,
        ),
    ),
    ("etf", re.compile(r"ETF", re.I)),
    ("irp", re.compile(r"IRP", re.I)),
    ("pension_savings", re.compile(r"연금\s*저축")),
)


def _glossary_term_id(message: str) -> str | None:
    """Identify a definition question such as "ETF가 뭐야?"."""

    if _GLOSSARY_QUESTION.search(message) is None:
        return None
    for term_id, pattern in _GLOSSARY_TERM_PATTERNS:
        if pattern.search(message) is not None:
            return term_id
    return None


_THEME_CANDIDATE_TERMS = re.compile(
    r"상품|종목|후보|추천|비교|보수|거래\s*대금|순자산", re.I
)
_THEME_ETF_LIST_TERMS = re.compile(
    r"(?:어떤|무슨)\s*ETF"
    r"|ETF\s*(?:상품\s*)?(?:은|는|이|가)?\s*"
    r"(?:뭐가|무엇이|어떤\s*게|어느\s*게).{0,8}(?:있|보여|알려)",
    re.I,
)
_THEME_HOLDING_TERMS = re.compile(
    r"구성\s*종목|편입\s*종목|보유\s*종목|종목\s*비중"
    r"|ETF.{0,8}대표\s*종목",
    re.I,
)
_THEME_REPRESENTATIVE_COMPANY_TERMS = re.compile(
    r"(?:대표|주요|관련)\s*(?:테마\s*)?(?:기업|회사)"
    r"|(?:기업|회사).{0,12}(?:뭐|무엇|어디|알려|소개)"
    r"|어떤\s*(?:기업|회사)|대표\s*종목"
)
_THEME_CONSIDERATION_TERMS = re.compile(
    r"(?:투자|편입).{0,15}(?:고려|주의|유의|살펴)"
    r"|(?:고려|주의|유의|살펴).{0,12}(?:점|사항)"
    r"|장단점|장점|이점"
)
_THEME_PERFORMANCE_DRIVER_TERMS = re.compile(
    r"(?:성과|수익|가격).{0,18}(?:영향|요인|좌우|움직)"
    r"|(?:영향|관찰|체크).{0,12}(?:요인|지표)"
    r"|가격\s*동인"
)
_THEME_RISK_TERMS = re.compile(
    r"고유\s*(?:위험|리스크)|핵심\s*(?:위험|리스크)"
    r"|주의할\s*(?:위험|리스크)|위험|리스크|단점"
)
_COMBINE_WORDS = (
    r"(?:합쳐(?:서)?|합산(?:해서)?|통합(?:해서)?|묶어(?:서)?|"
    r"전체(?:로)?|한꺼번에|둘을\s*같이|같이\s*묶어)"
)
_COMBINED_RULE_WORDS = r"(?:위험\s*자산|한도|70\s*%|규칙|적용|계산)"
_COMBINED_ACCOUNT_RULE = re.compile(
    rf"{_COMBINE_WORDS}.{{0,25}}{_COMBINED_RULE_WORDS}"
    rf"|{_COMBINED_RULE_WORDS}.{{0,25}}{_COMBINE_WORDS}"
)
_DISCLOSURE_TERMS = re.compile(r"공시|수익률|수수료|적립금|준비금|사업자|회사")
_NEWS_TERMS = re.compile(r"뉴스|기사|소식")
_NEWS_EVENT_STRATEGY_TERMS = re.compile(
    r"이벤트\s*드리븐|뉴스\s*기반|"
    r"실시간.{0,20}(?:운용|투자|포트폴리오|전략|리밸런싱)|"
    r"(?:운용|투자|포트폴리오|전략|리밸런싱).{0,20}실시간",
    re.I,
)
_NEWS_TIMELINESS_TERMS = re.compile(r"실시간|방금|장중", re.I)
_UNSUPPORTED_MARKET_NEWS = re.compile(
    r"(?:중국|일본|유럽|홍콩|대만)\s*(?:증시|시장|주식|뉴스|기사|소식)",
    re.I,
)
_PENSION_NEWS = re.compile(r"연금저축|퇴직연금|(?<![A-Za-z])IRP(?![A-Za-z])|DC형", re.I)
_COMPANY_NEWS = re.compile(
    r"삼성전자|SK\s*하이닉스|현대차|기아|LG에너지솔루션|NAVER|카카오",
    re.I,
)
_FOREIGN_MARKET_OR_INDIVIDUAL_STOCK = re.compile(
    r"(?:중국|일본|유럽|홍콩|대만)\s*(?:증시|시장|주식|투자|편입)"
    r"|(?:개별\s*주식|직접\s*주식).{0,20}(?:담|편입|투자|보유)"
    r"|(?:담|편입|투자|보유).{0,20}(?:개별\s*주식|직접\s*주식)"
    r"|(?:삼성전자|SK\s*하이닉스|현대차|기아|LG에너지솔루션|NAVER|카카오)"
    r".{0,20}(?:담|편입|투자|보유)",
    re.I,
)
_MACRO_EVIDENCE_TERMS = re.compile(
    r"기준\s*금리|소비자\s*물가|물가\s*상승률|인플레이션|"
    r"기대\s*수명|거시\s*(?:지표|환경)|연방\s*기금|"
    r"미국\s*10년\s*국채|기대\s*인플레이션|"
    r"유사\s*국면|과거\s*국면|최대\s*낙폭",
    re.I,
)
_RULE_TERMS = re.compile(
    r"규칙|제도|한도|세금|인출|차이|위험자산|예외|적격|연금|TDF", re.I
)
_PENSION_CONTEXT = re.compile(
    r"연금\s*(?:계좌|저축|수령|외\s*수령)|퇴직\s*연금|"
    r"(?<![A-Za-z])(?:IRP|DC)(?![A-Za-z])|세액\s*공제|"
    r"계좌.{0,20}(?:위험\s*자산|한도)",
    re.I,
)
_PENSION_BASICS_QUESTION = re.compile(
    r"(?:연금|퇴직\s*연금)\s*(?:이|은|는|을|를|의)?\s*"
    r"(?:뭐|무엇|종류|기본|제도|알려|설명|"
    r"어떻게\s*(?:시작|가입)|(?:시작|가입).{0,8}어떻게)",
    re.I,
)
_ACCOUNT_OVERVIEW_WORDS = re.compile(
    r"규칙|뭐|무엇|전체|전반|한눈에|정리|설명|알려|기본|차이|비교"
)
_ACCOUNT_OVERVIEW_NARROW_TERMS = re.compile(
    r"위험\s*자산|편입|적격|TDF|디폴트\s*옵션|중도\s*인출|"
    r"세액\s*공제|공제율|수령|개시|요건|조건|과세|세금|"
    r"수익률|수수료|공시|뉴스"
)
_PENSION_RECEIPT_START_TOPIC = re.compile(
    r"(?:연금|수령).{0,15}(?:언제|몇\s*살|몇\s*세|개시|시작)"
    r"|(?:언제|몇\s*살|몇\s*세|개시|시작).{0,15}(?:연금|수령)"
    r"|연금.{0,12}받을\s*수"
)
_PENSION_RECEIPT_TAX_TOPIC = re.compile(
    r"연금\s*(?:으로)?\s*받.{0,10}(?:세금|세율|과세)"
    r"|(?:세금|세율|과세).{0,10}연금\s*(?:으로)?\s*받"
)
_PRIVATE_PENSION_THRESHOLD_TOPIC = re.compile(
    r"(?:사적\s*연금|연금\s*소득).{0,20}1\s*,?\s*500\s*만\s*원"
    r"|1\s*,?\s*500\s*만\s*원.{0,20}(?:사적\s*연금|연금\s*소득)"
)
_NON_PENSION_WITHDRAWAL_TOPIC = re.compile(
    r"(?:IRP|DC형?|연금저축|연금\s*계좌)?.{0,8}"
    r"(?:중도\s*인출|중도\s*해지|해지).{0,8}(?:하면|어떻게|세금은)",
    re.I,
)
_SCENARIO_TERMS = re.compile(
    r"목\s*계좌|모의\s*계좌|내\s*(?:연금\s*)?포트폴리오|"
    r"나의\s*(?:연금\s*)?포트폴리오|포트폴리오\s*진단|계좌\s*진단|"
    r"(?:IRP|연금저축).{0,20}수익률.{0,12}진단|"
    r"시나리오|미\s*운용|방치|편중|중복"
)
_EDUCATIONAL_PORTFOLIO_TERMS = re.compile(
    r"연금\s*(?:운용|투자)\s*(?:전략)?|연금\s*저축\s*전략|"
    r"운용\s*전략|투자\s*전략|"
    r"포트폴리오|자산\s*배분|투자\s*(?:성향|스타일)|"
    r"안정\s*추구형|위험\s*중립형|적극\s*투자형|"
    r"공격\s*투자형|안정형"
)
# 나이를 밝히고 운용 방법을 묻는 표현. 타깃 사용자는 "35살인데 어떻게
# 배분해?"처럼 전략·포트폴리오라는 말 없이 묻는다. 나이와 운용 동사가
# 함께 있을 때만 전략 안내로 본다.
_AGE_BASED_ALLOCATION_QUESTION = re.compile(
    r"(?:\d{2})\s*(?:살|세)[^?]{0,20}"
    r"(?:어떻게|어떤|뭐가|무엇이|어느)[^?]{0,12}"
    r"(?:배분|운용|굴려|굴리|투자|담아|담으|시작|전략|맞아|좋아|하지|해야)"
)
_TAX_CREDIT_TERMS = re.compile(
    r"세액\s*공제|절세\s*혜택|공제\s*혜택|공제\s*한도|"
    # "세액"을 생략하고 "공제 얼마야?"처럼 축약해 물어도 세액공제 계산으로
    # 인식한다. "공제" 단독 오분류(예: 중도해지 맥락)를 막기 위해 계산·금액을
    # 묻는 신호가 가까이 있을 때만 매칭한다.
    r"공제(?:액|율)?\s*(?:은|는|이|가)?\s*"
    r"(?:얼마|금액|계산|환급|돌려\s*받|받을\s*수)"
)
# "공제"라는 말조차 모르는 입문자는 "900만원 넣으면 얼마 돌려받아?"처럼
# 묻는다. 납입 금액과 환급을 묻는 표현이 함께 있을 때만 세액공제로 본다.
_CONTRIBUTION_REFUND_QUESTION = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:억|천만|만|천)?\s*원[^?]{0,20}"
    r"(?:넣|납입|입금|저축|불입)[^?]{0,20}"
    r"(?:얼마|환급|돌려\s*받|아끼|절세|혜택)"
)
_WITHDRAWAL_TAX_TERMS = re.compile(
    r"중도\s*해지|연금\s*외\s*수령|해지.{0,10}(?:세금|세액|과세)|"
    r"(?:세금|세액|과세).{0,10}해지|16\.5\s*%"
)
_PENSION_TAX_CALCULATION_TERMS = re.compile(
    r"계산|얼마|공제액|과세액|예상\s*(?:세액|금액)|환급액|돌려\s*받|"
    r"받을\s*수\s*있는|"
    r"\d[\d,]*(?:\.\d+)?\s*(?:억|천만|만|천)?\s*원"
)
_MISSED_TAX_CREDIT_TERMS = re.compile(
    r"놓치.{0,12}(?:세액\s*공제|공제)\s*혜택|"
    r"(?:세액\s*공제|공제)\s*혜택.{0,12}놓치"
)
_PENSION_PLANNER_TERMS = re.compile(
    r"(?:적립|모으).{0,16}(?:얼마|계산|시뮬)|"
    r"(?:55|60|65)\s*세.{0,16}(?:얼마|수령|계산)|"
    r"(?:수령액|연금\s*계산|시뮬레이션).{0,16}(?:얼마|계산|알려)"
)
_DISTRIBUTION_TERMS = re.compile(
    r"분배\s*(?:금|락|기준일|지급일|일정)|배당\s*(?:금|락|기준일|지급일|일정)|"
    r"지급\s*일|재\s*투자",
    re.I,
)
_ETF_ISU_CODE = re.compile(r"(?<![0-9A-Z])([0-9A-Z]{6})(?![0-9A-Z])", re.I)
_REINVESTMENT_TERMS = re.compile(r"(?:분배금|배당금)?\s*재투자", re.I)
_REINVESTMENT_QUANTITY = re.compile(
    r"(?:보유\s*)?수량\s*[:=]\s*([0-9][0-9,]*(?:\.\d+)?)\s*(?:주)?",
    re.I,
)
_REINVESTMENT_PRICE = re.compile(
    r"(?:재투자\s*)?기준가\s*[:=]\s*([0-9][0-9,]*(?:\.\d+)?)\s*(?:원|krw)?",
    re.I,
)
_REINVESTMENT_AS_OF = re.compile(r"기준일\s*[:=]\s*(\d{4}-\d{2}-\d{2})")
_REINVESTMENT_REBALANCE_ON = re.compile(
    r"리밸런싱\s*일\s*[:=]\s*(\d{4}-\d{2}-\d{2})",
    re.I,
)
_COUNT = re.compile(r"(?<!\d)([1-5])\s*(?:개|건)(?:만)?(?!\d)")
_KOREAN_COUNT = (
    (re.compile(r"(?:한\s*(?:개|건)|하나)(?:만)?"), 1),
    (re.compile(r"(?:두\s*(?:개|건)|둘)(?:만)?"), 2),
    (re.compile(r"(?:세\s*(?:개|건)|셋)(?:만)?"), 3),
    (re.compile(r"(?:네\s*(?:개|건)|넷)(?:만)?"), 4),
    (re.compile(r"(?:다섯\s*(?:개|건))(?:만)?"), 5),
)
_INTENT_PRIORITY = (
    ChatIntent.MOCK_PORTFOLIO,
    ChatIntent.PENSION_TAX,
    ChatIntent.ETF_DISTRIBUTION,
    ChatIntent.NEWS,
    ChatIntent.MACRO_EVIDENCE,
    ChatIntent.ETF_THEME,
    ChatIntent.EDUCATIONAL_PORTFOLIO,
    ChatIntent.PROVIDER_DISCLOSURE,
    ChatIntent.ACCOUNT_RULE,
)


def _account_types(message: str) -> tuple[AccountType, ...]:
    found: list[AccountType] = []
    if re.search(r"(?<![A-Za-z])DC(?![A-Za-z])|확정기여형", message, re.I):
        found.append(AccountType.DC)
    if re.search(r"(?<![A-Za-z])IRP(?![A-Za-z])|개인형\s*퇴직연금", message, re.I):
        found.append(AccountType.IRP)
    if "연금저축" in message:
        found.append(AccountType.PENSION_SAVINGS)
    return tuple(found)


def is_missed_tax_credit_question(message: str) -> bool:
    return _MISSED_TAX_CREDIT_TERMS.search(message) is not None


def _contains_sensitive_information(message: str) -> bool:
    return (
        _RRN.search(message) is not None
        or _PHONE.search(message) is not None
        or _EMAIL.search(message) is not None
        or any(pattern.search(message) for pattern in _SENSITIVE_VALUE_PATTERNS)
    )


def _max_results(message: str, default: int) -> int:
    match = _COUNT.search(message)
    if match is not None:
        return int(match.group(1))
    for pattern, value in _KOREAN_COUNT:
        if pattern.search(message):
            return value
    return max(1, min(default, 5))


def _news_query(message: str) -> str:
    if re.search(r"미국|뉴욕|나스닥|S\s*&\s*P|다우", message, re.I):
        return "market:us"
    if re.search(r"한국|국내|코스피|코스닥", message, re.I):
        return "market:kr"
    return "market"


def _distribution_isu_code(message: str) -> str | None:
    match = _ETF_ISU_CODE.search(message)
    return match.group(1).upper() if match is not None else None


def _distribution_reinvestment_request(
    message: str,
    *,
    isu_code: str | None,
) -> DistributionReinvestmentRequest | None:
    if not _REINVESTMENT_TERMS.search(message) or isu_code is None:
        return None
    quantity = _REINVESTMENT_QUANTITY.search(message)
    price = _REINVESTMENT_PRICE.search(message)
    as_of = _REINVESTMENT_AS_OF.search(message)
    rebalance_on = _REINVESTMENT_REBALANCE_ON.search(message)
    if not all((quantity, price, as_of, rebalance_on)):
        return None
    try:
        return DistributionReinvestmentRequest(
            isu_code=isu_code,
            quantity=Decimal(quantity.group(1).replace(",", "")),
            reinvestment_price_krw=Decimal(price.group(1).replace(",", "")),
            as_of=date.fromisoformat(as_of.group(1)),
            rebalance_on=date.fromisoformat(rebalance_on.group(1)),
        )
    except (InvalidOperation, ValueError):
        return None


def _news_scope_notice(message: str) -> NewsScopeNotice | None:
    if _PENSION_NEWS.search(message):
        return NewsScopeNotice.PENSION
    if _UNSUPPORTED_MARKET_NEWS.search(message):
        return NewsScopeNotice.UNSUPPORTED_MARKET
    if _COMPANY_NEWS.search(message):
        return NewsScopeNotice.COMPANY
    return None


def _account_rule_topic(
    message: str, account_types: tuple[AccountType, ...]
) -> AccountRuleTopic | None:
    if _PENSION_BASICS_QUESTION.search(message):
        return AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW
    if _PENSION_RECEIPT_TAX_TOPIC.search(message):
        return AccountRuleTopic.PENSION_RECEIPT_TAX
    if _PENSION_RECEIPT_START_TOPIC.search(message) and not re.search(
        r"요건|조건", message
    ):
        return AccountRuleTopic.PENSION_RECEIPT_START
    if _PRIVATE_PENSION_THRESHOLD_TOPIC.search(message):
        return AccountRuleTopic.PRIVATE_PENSION_THRESHOLD
    if _NON_PENSION_WITHDRAWAL_TOPIC.search(message):
        return AccountRuleTopic.NON_PENSION_WITHDRAWAL
    if _ACCOUNT_OVERVIEW_NARROW_TERMS.search(message):
        return None
    asks_for_overview = _ACCOUNT_OVERVIEW_WORDS.search(message) is not None
    compares_all_accounts = set(account_types) == {
        AccountType.DC,
        AccountType.IRP,
        AccountType.PENSION_SAVINGS,
    }
    if asks_for_overview and (
        re.search(r"연금\s*계좌", message) or compares_all_accounts
    ):
        return AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW
    return None


def _blocked(message: str, reason: BlockedReason, max_results: int) -> QueryPlan:
    return QueryPlan(
        normalized_message=message,
        intent=ChatIntent.OUT_OF_SCOPE,
        max_results=max_results,
        blocked_reason=reason,
    )


def plan_question(
    message: str,
    *,
    default_max_results: int = 3,
    structured_pension_tax: bool = False,
    theme_repository: EtfThemeRepository | None = None,
) -> QueryPlan:
    normalized = normalize_search_text(message)
    max_results = _max_results(normalized, default_max_results)
    if not normalized:
        return _blocked("질문 없음", BlockedReason.UNSUPPORTED, max_results)
    if theme_repository is not None:
        theme = theme_repository.resolve(normalized)
    else:
        try:
            theme = get_default_etf_theme_repository().resolve(normalized)
        except (FileNotFoundError, ValueError):
            theme = None
    blocking_rules = (
        (
            _contains_sensitive_information(normalized),
            BlockedReason.SENSITIVE_INFORMATION,
        ),
        (_ORDER_REQUEST.search(normalized) is not None, BlockedReason.ORDER_REQUEST),
        (
            _FUTURE_PREDICTION.search(normalized) is not None,
            BlockedReason.FUTURE_PREDICTION,
        ),
        (
            _FOREIGN_MARKET_OR_INDIVIDUAL_STOCK.search(normalized) is not None
            and _NEWS_TERMS.search(normalized) is None,
            BlockedReason.FOREIGN_MARKET_OR_INDIVIDUAL_STOCK,
        ),
        (
            _PRODUCT_LEVEL.search(normalized) is not None and theme is None,
            BlockedReason.PRODUCT_LEVEL_UNAVAILABLE,
        ),
    )
    for matched, reason in blocking_rules:
        if matched:
            return _blocked(normalized, reason, max_results)

    account_types = _account_types(normalized)
    account_rule_topic = _account_rule_topic(normalized, account_types)
    tax_credit_topic = _TAX_CREDIT_TERMS.search(normalized) is not None
    if not tax_credit_topic and _CONTRIBUTION_REFUND_QUESTION.search(normalized):
        # 납입 금액과 환급을 함께 물으면 세액공제 계산이 답이다. 중도해지
        # 세금 질문을 가로채지 않도록 해지 표현이 없을 때만 적용한다.
        tax_credit_topic = _WITHDRAWAL_TAX_TERMS.search(normalized) is None
    withdrawal_tax_topic = _WITHDRAWAL_TAX_TERMS.search(normalized) is not None
    requests_calculation = _PENSION_TAX_CALCULATION_TERMS.search(
        normalized
    ) is not None or is_missed_tax_credit_question(normalized)
    has_calculation_input = structured_pension_tax or requests_calculation
    requests_tax_credit = tax_credit_topic and has_calculation_input
    requests_withdrawal_tax = withdrawal_tax_topic and has_calculation_input
    requests_pension_planner = _PENSION_PLANNER_TERMS.search(normalized) is not None
    if structured_pension_tax and not (tax_credit_topic or withdrawal_tax_topic):
        requests_tax_credit = True
        requests_withdrawal_tax = True
    intent_matches = {
        ChatIntent.MOCK_PORTFOLIO: _SCENARIO_TERMS.search(normalized) is not None,
        ChatIntent.PENSION_TAX: requests_tax_credit or requests_withdrawal_tax,
        ChatIntent.ETF_DISTRIBUTION: _DISTRIBUTION_TERMS.search(normalized) is not None,
        ChatIntent.NEWS: (
            _NEWS_TERMS.search(normalized) is not None
            or _NEWS_EVENT_STRATEGY_TERMS.search(normalized) is not None
        ),
        ChatIntent.ETF_THEME: theme is not None,
        ChatIntent.MACRO_EVIDENCE: (
            _MACRO_EVIDENCE_TERMS.search(normalized) is not None
        ),
        ChatIntent.EDUCATIONAL_PORTFOLIO: (
            _EDUCATIONAL_PORTFOLIO_TERMS.search(normalized) is not None
            or _AGE_BASED_ALLOCATION_QUESTION.search(normalized) is not None
        ),
        ChatIntent.PROVIDER_DISCLOSURE: bool(account_types)
        and _DISCLOSURE_TERMS.search(normalized) is not None,
        ChatIntent.ACCOUNT_RULE: bool(
            requests_pension_planner
            or account_types
            or account_rule_topic
            or (_PENSION_CONTEXT.search(normalized) and _RULE_TERMS.search(normalized))
        ),
    }
    personal_account_tax_request = (
        intent_matches[ChatIntent.PENSION_TAX]
        and re.search(r"내\s*계좌", normalized) is not None
    )
    # "내 계좌"는 목시나리오 선택에도 쓰이지만 명시적 세금 요청과 함께면
    # 세금 계산 의도가 더 구체적이다. 전역 우선순위는 유지해 다른 복합 질문의
    # 기존 라우팅 범위를 넓히지 않는다.
    intent = (
        ChatIntent.PENSION_TAX
        if personal_account_tax_request
        else next(
            (candidate for candidate in _INTENT_PRIORITY if intent_matches[candidate]),
            None,
        )
    )

    if intent == ChatIntent.MOCK_PORTFOLIO:
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.MOCK_PORTFOLIO,
            account_types=account_types,
            max_results=max_results,
        )
    if intent == ChatIntent.PENSION_TAX:
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.PENSION_TAX,
            account_types=account_types,
            max_results=max_results,
            requests_tax_credit=requests_tax_credit,
            requests_withdrawal_tax=requests_withdrawal_tax,
        )
    if intent == ChatIntent.ETF_DISTRIBUTION:
        isu_code = _distribution_isu_code(normalized)
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.ETF_DISTRIBUTION,
            account_types=account_types,
            max_results=max_results,
            distribution_isu_code=isu_code,
            distribution_reinvestment=_distribution_reinvestment_request(
                normalized,
                isu_code=isu_code,
            ),
        )
    if intent == ChatIntent.NEWS:
        news_query = _news_query(normalized)
        requests_event_strategy = (
            _NEWS_EVENT_STRATEGY_TERMS.search(normalized) is not None
        )
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.NEWS,
            account_types=account_types,
            news_query=news_query,
            requests_event_strategy=requests_event_strategy,
            requests_live_news=requests_event_strategy,
            news_scope_notice=_news_scope_notice(normalized),
            max_results=max_results,
        )
    if intent == ChatIntent.MACRO_EVIDENCE:
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.MACRO_EVIDENCE,
            account_types=account_types,
            max_results=max_results,
        )
    if intent == ChatIntent.ETF_THEME:
        assert theme is not None
        requests_holdings = _THEME_HOLDING_TERMS.search(normalized) is not None
        asks_representative_companies = (
            _THEME_REPRESENTATIVE_COMPANY_TERMS.search(normalized) is not None
        )
        asks_considerations = _THEME_CONSIDERATION_TERMS.search(normalized) is not None
        asks_performance_drivers = (
            _THEME_PERFORMANCE_DRIVER_TERMS.search(normalized) is not None
        )
        asks_risks = _THEME_RISK_TERMS.search(normalized) is not None
        requests_candidates = requests_holdings or (
            not asks_representative_companies
            and not asks_considerations
            and not asks_performance_drivers
            and not asks_risks
            and (
                _THEME_CANDIDATE_TERMS.search(normalized) is not None
                or _THEME_ETF_LIST_TERMS.search(normalized) is not None
            )
        )
        content_topic = (
            ThemeContentTopic.OVERVIEW
            if requests_candidates
            else ThemeContentTopic.REPRESENTATIVE_COMPANIES
            if asks_representative_companies
            else ThemeContentTopic.PERFORMANCE_DRIVERS
            if asks_performance_drivers
            else ThemeContentTopic.INVESTMENT_CONSIDERATIONS
            if asks_considerations
            else ThemeContentTopic.RISKS
            if asks_risks
            else ThemeContentTopic.OVERVIEW
        )
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.ETF_THEME,
            account_types=account_types,
            max_results=3 if requests_candidates else max_results,
            theme_id=theme.theme_id,
            theme_content_topic=content_topic,
            requests_theme_candidates=requests_candidates,
            requests_theme_holdings=requests_holdings,
        )
    if intent == ChatIntent.EDUCATIONAL_PORTFOLIO:
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
            account_types=account_types,
            max_results=max_results,
        )
    if intent == ChatIntent.PROVIDER_DISCLOSURE:
        if len(account_types) > 1:
            return _blocked(
                normalized,
                BlockedReason.ACCOUNT_SELECTION_REQUIRED,
                max_results,
            )
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.PROVIDER_DISCLOSURE,
            account_types=account_types,
            max_results=max_results,
        )
    if intent == ChatIntent.ACCOUNT_RULE:
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.ACCOUNT_RULE,
            account_types=account_types,
            max_results=max_results,
            combines_account_rules=(
                len(account_types) > 1
                and _COMBINED_ACCOUNT_RULE.search(normalized) is not None
            ),
            account_rule_topic=account_rule_topic,
            requests_pension_planner=requests_pension_planner,
        )
    # 기존 인텐트가 모두 받지 않은 뒤에만 용어 질문으로 본다. 계좌·세액
    # 질문을 가로채지 않도록 차단 직전에 둔다.
    glossary_term_id = _glossary_term_id(normalized)
    if glossary_term_id is not None:
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.GLOSSARY,
            max_results=max_results,
            glossary_term_id=glossary_term_id,
        )
    # 어떤 인텐트도 받지 못했고 용어도 특정되지 않은 질문 가운데 "뭐부터
    # 해야 할지 모르겠어"처럼 시작점을 묻는 것은 차단 대신 안내로 받는다.
    if _is_getting_started_question(normalized):
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.GETTING_STARTED,
            max_results=max_results,
        )
    return _blocked(normalized, BlockedReason.UNSUPPORTED, max_results)
