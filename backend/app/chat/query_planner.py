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
from ..text_normalization import normalize_colloquial_text
from .models import ChatIntent


class BlockedReason(StrEnum):
    SENSITIVE_INFORMATION = "sensitive_information"
    FUTURE_PREDICTION = "future_prediction"
    ORDER_REQUEST = "order_request"
    FOREIGN_MARKET_OR_INDIVIDUAL_STOCK = "foreign_market_or_individual_stock"
    PRODUCT_LEVEL_UNAVAILABLE = "product_level_unavailable"
    ACCOUNT_SELECTION_REQUIRED = "account_selection_required"
    CONTRIBUTION_AMOUNT_ADVICE = "contribution_amount_advice"
    FEE_TARGET_REQUIRED = "fee_target_required"
    PROVIDER_CHOICE_ADVICE = "provider_choice_advice"
    PERSONAL_ALLOCATION_ADVICE = "personal_allocation_advice"
    PRINCIPAL_GUARANTEE_QUESTION = "principal_guarantee_question"
    REFERENT_SELECTION_REQUIRED = "referent_selection_required"
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
    requests_strategy_rationale: bool = False
    distribution_isu_code: str | None = None
    distribution_reinvestment: DistributionReinvestmentRequest | None = None
    glossary_term_id: str | None = None
    investing_principle_id: str | None = None
    hesitation_answer_id: str | None = None
    blocked_reason: BlockedReason | None = None

    @model_validator(mode="after")
    def verify_intent_fields(self) -> "QueryPlan":
        if self.intent == ChatIntent.NEWS and self.news_query is None:
            raise ValueError("news intent requires news_query")
        if self.intent == ChatIntent.GLOSSARY and self.glossary_term_id is None:
            raise ValueError("glossary intent requires glossary_term_id")
        if self.intent != ChatIntent.GLOSSARY and self.glossary_term_id is not None:
            raise ValueError("glossary_term_id is only valid for glossary intent")
        if (
            self.intent == ChatIntent.INVESTING_PRINCIPLE
            and self.investing_principle_id is None
        ):
            raise ValueError(
                "investing principle intent requires investing_principle_id"
            )
        if (
            self.intent != ChatIntent.INVESTING_PRINCIPLE
            and self.investing_principle_id is not None
        ):
            raise ValueError(
                "investing_principle_id is only valid for investing principle intent"
            )
        if (
            self.intent == ChatIntent.HESITATION_SUPPORT
            and self.hesitation_answer_id is None
        ):
            raise ValueError("hesitation support intent requires hesitation_answer_id")
        if (
            self.intent != ChatIntent.HESITATION_SUPPORT
            and self.hesitation_answer_id is not None
        ):
            raise ValueError(
                "hesitation_answer_id is only valid for hesitation support intent"
            )
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
        if (
            self.requests_strategy_rationale
            and self.intent != ChatIntent.EDUCATIONAL_PORTFOLIO
        ):
            raise ValueError(
                "strategy rationale requires educational_portfolio intent"
            )
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
    r"매수해|매도해|주문해|사\s*줘|팔아\s*줘|대신\s*사|대신\s*팔|자동\s*투자|"
    r"주문\s*(?:넣|실행|처리)|(?:매수|매도).{0,12}(?:실행|진행|처리)"
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
    r"뭐가\s*달라|무엇이\s*다른|차이(?:가|는)?\s*(?:뭐|무엇)|"
    r"안\s*(?:돼|되)|괜찮(?:아|을까)|해도\s*(?:돼|되)"
)
# 정의를 묻는 것이 분명한 어미. 이 신호가 있으면 데이터 조회 인텐트보다
# 용어 설명이 앞선다. "채권이 뭐야?"에 ETF 카탈로그를 주지 않기 위함이다.
_DEFINITION_QUESTION = re.compile(
    r"(?:이|가|은|는|란|이란)?\s*"
    r"(?:뭐(?:야|예요|에요|지|니|냐)|무슨\s*(?:말|뜻)|"
    r"뜻이?\s*(?:뭐|무엇)|어떤\s*(?:의미|뜻)|무엇(?:인가|이야|이에요)?)"
    r"|뭐가\s*달라|차이(?:가|는)?\s*(?:뭐|무엇)"
)
# 뜻풀이에 자리를 내줄 수 있는 인텐트. 상품·수치 조회라서 정의 질문에는
# 답이 되지 않는다. 계좌 규칙·세액 계산은 제도 설명이 더 정확하므로 뺀다.
_DEFINITION_OVERRIDABLE_INTENTS = frozenset(
    {
        ChatIntent.ETF_THEME,
        ChatIntent.MACRO_EVIDENCE,
        ChatIntent.EDUCATIONAL_PORTFOLIO,
        ChatIntent.ETF_DISTRIBUTION,
    }
)
# "채권"처럼 테마 이름이면서 기초 용어인 말이 있다. ETF·테마·상품을 함께
# 언급하면 카탈로그 질문, 그렇지 않으면 용어 질문으로 본다.
_PRODUCT_LOOKUP_CONTEXT = re.compile(
    r"ETF|테마|상품|종목|후보|담을|투자할|편입", re.I
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
    # 경제·투자 기초 용어. 더 긴 표현이 짧은 표현에 먹히지 않도록
    # 구체적인 것부터 둔다("연평균 수익률"이 "수익률"보다 앞).
    ("annualized_return", re.compile(r"연\s*평균\s*수익률")),
    ("compound_interest", re.compile(r"복리")),
    ("simple_interest", re.compile(r"단리")),
    ("asset_allocation", re.compile(r"자산\s*배분")),
    ("diversification", re.compile(r"분산\s*투자")),
    ("installment_investing", re.compile(r"적립식|적립\s*투자")),
    ("volatility", re.compile(r"변동성")),
    ("currency_hedge", re.compile(r"환\s*헤지|환헷지")),
    ("exchange_rate", re.compile(r"환율")),
    ("inflation", re.compile(r"인플레이션|물가\s*상승")),
    ("interest_rate", re.compile(r"금리|이자율")),
    ("market_cap", re.compile(r"시가\s*총액")),
    ("dividend", re.compile(r"배당(?!\s*상품)")),
    ("kospi", re.compile(r"코스피|KOSPI", re.I)),
    ("kosdaq", re.compile(r"코스닥|KOSDAQ", re.I)),
    ("sp500", re.compile(r"S\s*&\s*P\s*500|에스\s*앤\s*피\s*500", re.I)),
    ("nasdaq", re.compile(r"나스닥|NASDAQ", re.I)),
    ("index", re.compile(r"지수")),
    ("bond", re.compile(r"채권")),
    ("stock", re.compile(r"주식")),
    ("fund", re.compile(r"펀드")),
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
    r"(?:연금|퇴직\s*연금)\s*(?:이란|이라는|이|은|는|을|를|의)?\s*"
    r"(?:뭐|뭔지|무엇|종류|기본|제도|알려|설명|"
    r"어떻게\s*(?:시작|가입)|(?:시작|가입).{0,8}어떻게)",
    re.I,
)
# 타깃 사용자는 "중도인출"이 아니라 "돈 필요하면 뺄 수 있어?"라고 묻는다.
# 제도 용어를 몰라도 계좌 규칙 안내에 닿도록 일상어 표현을 함께 받는다.
# 각 표현이 연금계좌에서만 성립하는 행위(납입 중단·중도인출·일시금 수령 등)를
# 가리키므로 별도 문맥 단어를 요구하지 않는다. 대신 표현 자체를 좁게 유지한다.
_PENSION_PRACTICE_QUESTION = re.compile(
    # 개설·준비
    r"계좌.{0,10}(?:여러\s*개|두\s*개|하나만|개수|몇\s*개)"
    r"|(?:여러\s*개|두\s*개|몇\s*개).{0,10}(?:만들|개설|가입)"
    r"|(?:만들|개설|가입).{0,10}(?:뭐|무엇|어떤).{0,6}(?:준비|필요|있어야)"
    r"|(?:준비물|필요\s*서류)"
    # 납입 유연성
    r"|(?:한\s*달|매달|다달이|이번\s*달).{0,12}"
    r"(?:걸러|거르|쉬|건너뛰|안\s*넣|못\s*넣)"
    r"|(?:몰아서|한꺼번에|한\s*번에).{0,12}(?:넣|납입|입금)"
    r"|한도.{0,10}(?:넘|초과).{0,12}(?:넣|납입)"
    r"|(?:넣|납입).{0,12}(?:쉬어|쉬면|멈|중단|안\s*해도)"
    # 중도인출·담보
    r"|(?:돈|자금|목돈).{0,14}(?:빼|뺄|뺴|찾|인출|쓸|써야|필요)"
    r"[^?]{0,14}(?:빼|뺄|찾|인출|쓸|대출|돼|되|있어)"
    r"|(?:중간|중도|급하|갑자기).{0,14}(?:빼|뺄|찾|인출)"
    r"|담보\s*대출|담보.{0,8}대출"
    # 상품 변경·비용
    r"|(?:상품|펀드|ETF).{0,10}(?:바꾸|바꿀|바꿔|바꿨|교체|변경|갈아타)"
    r"|(?:바꾸|바꿀|바꿔|바꾸면|교체|변경).{0,10}수수료"
    # 이전 시 보유 상품 처리
    r"|(?:옮기|옮길|이전).{0,12}(?:상품|펀드|ETF).{0,12}"
    r"(?:팔|현금화|해지|정리)"
    # 연말정산·수령 방식
    r"|연말\s*정산"
    r"|(?:한\s*번에|한꺼번에).{0,10}(?:다|전부|모두)?\s*(?:받|찾|수령)"
    r"|일시금",
    re.I,
)
# 조언형 대안 응답에서 제외할 자산. 연금계좌에서 다루지 않는 대상을 콕 집어
# 물으면 기존 안전 폴백을 그대로 유지한다("비트코인 지금 사도 돼?").
# 문맥어를 요구하는 대신 제외 목록을 쓰는 이유는, 정작 도움이 필요한 질문이
# "뭐 사야 돼?"처럼 짧고 문맥어가 없기 때문이다.
_NON_PENSION_ASSET = re.compile(
    r"비트\s*코인|코인|암호\s*화폐|가상\s*자산|이더리움|알트코인"
    r"|부동산|아파트|주택\s*청약|청약\s*통장|전세|월세|토지|상가"
    r"|로또|복권|도박|경마",
    re.I,
)
# 정답이 사람마다 다른 조언형 질문. 특정 금액을 권유하지 않고 세액공제
# 한도라는 공식 기준점을 제시한 뒤 계산기로 넘긴다.
_PRINCIPLE_WHY_QUESTION = re.compile(
    r"왜|이유(?:가|는)?|뭐가\s*좋|무슨\s*소용|어떤\s*점이\s*좋"
    r"|얼마나\s*(?:영향|중요)|영향(?:을|이)?\s*(?:주|줘|미치)"
    r"|(?:좋|필요|해야)(?:은|는)?\s*(?:이유|까닭)",
    re.I,
)
# "왜 그렇게 하는가"에 답할 원리. 구체적인 표현을 먼저 두어 넓은 표현이
# 가로채지 않게 한다.
_INVESTING_PRINCIPLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fee_impact", re.compile(r"수수료|보수|비용")),
    ("compounding_time", re.compile(r"복리")),
    (
        "young_risk_weight",
        re.compile(r"(?:젊|어릴|20대|30대)[^?]{0,16}(?:주식|위험\s*자산|비중)"),
    ),
    (
        "age_safe_asset",
        re.compile(r"(?:나이|늙|은퇴|50대|60대)[^?]{0,16}(?:안전\s*자산|줄)"),
    ),
    ("why_currency_hedge", re.compile(r"환\s*헤지|환헷지")),
    ("why_rebalance", re.compile(r"리\s*밸런싱|리밸런스")),
    ("installment_effect", re.compile(r"적립식|나눠\s*사|분할\s*매수")),
    (
        "concentration_risk",
        re.compile(r"(?:한\s*(?:곳|군데|종목)|몰아|집중)[^?]{0,12}(?:넣|투자|담)"),
    ),
    ("long_term_investing", re.compile(r"장기\s*투자|오래\s*(?:들고|가지|묻어)")),
    ("why_diversify", re.compile(r"분산\s*투자|나눠\s*담")),
    (
        "risk_return_tradeoff",
        re.compile(r"위험[^?]{0,10}(?:줄이|낮추)[^?]{0,12}수익|수익[^?]{0,10}위험"),
    ),
)


def _investing_principle_id(message: str) -> str | None:
    """Identify a "why do we do this?" question about investing basics."""

    # 위험·수익 관계는 "왜"라는 말 없이 "줄이면 줄어?"처럼 묻는 경우가 많다.
    tradeoff = dict(_INVESTING_PRINCIPLE_PATTERNS)["risk_return_tradeoff"]
    if tradeoff.search(message) is not None:
        return "risk_return_tradeoff"
    if _PRINCIPLE_WHY_QUESTION.search(message) is None:
        return None
    for principle_id, pattern in _INVESTING_PRINCIPLE_PATTERNS:
        if pattern.search(message) is not None:
            return principle_id
    return None


_CONTRIBUTION_AMOUNT_ADVICE = re.compile(
    r"(?:한\s*달|매달|매월|월|다달이).{0,12}얼마"
    r"|얼마(?:씩|나)?.{0,12}(?:넣|납입|저축|모으).{0,12}(?:좋|나은|될까|할까|괜찮)"
    r"|(?:넣|납입|저축).{0,12}얼마.{0,12}(?:좋|나은|될까|할까|적당)"
    r"|적정.{0,8}(?:납입|금액)",
    re.I,
)
_FEE_TARGET_REQUIRED = re.compile(
    r"(?:수수료|총\s*보수|보수|비용).{0,12}"
    r"(?:얼마|몇\s*(?:퍼센트|%|원)|떼|나가|빠져)"
    r"|(?:얼마|몇\s*(?:퍼센트|%|원)).{0,12}"
    r"(?:수수료|총\s*보수|보수|비용)",
    re.I,
)
# 망설임이 담긴 질문. 감정을 단정하지 않고 승인된 사실로 답한다. 구체적인
# 표현을 앞에 두어 넓은 표현이 가로채지 않게 한다.
_HESITATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "peer_comparison",
        re.compile(
            r"남들?(?:은|이|보다)?[^?]{0,12}(?:얼마|어디|모으|모았|넣|투자|해)"
            r"|또래[^?]{0,12}(?:얼마|어디|모으|모았|넣)"
            r"|다들[^?]{0,12}(?:어디|얼마|투자|넣)"
            r"|평균(?:이|은)?[^?]{0,8}얼마"
            r"|친구[^?]{0,12}(?:수익|벌|났)"
            r"|나만[^?]{0,8}(?:늦|뒤처|못)",
            re.I,
        ),
    ),
    (
        "doing_well_check",
        re.compile(
            r"(?:내가|제가)?[^?]{0,6}잘\s*(?:하고|되고)\s*있"
            r"|이\s*정도(?:면|로)?[^?]{0,10}(?:괜찮|되|맞|충분)"
            r"|(?:내|제)[^?]{0,8}수익률[^?]{0,10}(?:낮|적|안\s*좋|괜찮)"
            r"|제대로\s*(?:하고|가고)\s*있",
            re.I,
        ),
    ),
    (
        "too_late_to_start",
        re.compile(
            r"(?:너무)?\s*늦(?:었|은|지|나|었나)"
            r"|지금\s*(?:시작|해도|가입)[^?]{0,10}(?:늦|괜찮|돼|될까|의미)"
            r"|\d{2}대(?:인데|라도|에)?[^?]{0,12}(?:늦|해도|시작|의미|되)"
            r"|나이(?:가)?\s*(?:많|들)[^?]{0,12}(?:의미|늦|해도|되)"
            r"|언제\s*시작(?:하는|해)[^?]{0,8}(?:좋|나)"
            r"|(?:조금)?\s*더\s*기다(?:렸다|려)",
            re.I,
        ),
    ),
    (
        "small_amount_start",
        re.compile(
            r"돈(?:이)?\s*(?:적|없|부족)[^?]{0,14}(?:시작|해도|넣|되|할\s*수)"
            r"|월급(?:이)?\s*(?:적|작)[^?]{0,14}(?:해도|되|할\s*수|넣)"
            r"|\d+\s*(?:만\s*)?원(?:으로|이라도|밖에)[^?]{0,10}(?:되|해도|시작|가능)"
            r"|소액(?:으로|이라도)?[^?]{0,10}(?:되|해도|시작|가능)"
            r"|조금씩(?:이라도)?[^?]{0,10}(?:되|해도|시작|가능)",
            re.I,
        ),
    ),
    (
        "market_drop_fear",
        re.compile(
            r"폭락|급락|떨어지면|내리면|하락하면"
            r"|시장(?:이)?\s*(?:불안|안\s*좋|흔들)"
            r"|(?:요즘|지금)[^?]{0,10}불안"
            r"|(?:지금|요즘)[^?]{0,10}(?:비싸|비싼|고점|많이\s*올라)"
            r"|(?:비싸|비싼)[^?]{0,10}(?:것|거)\s*같"
            r"|마이너스[^?]{0,12}(?:났|나면|인데|어떡)",
            re.I,
        ),
    ),
    (
        "loss_fear",
        re.compile(
            r"손실[^?]{0,12}(?:나면|났|어떡|어떻|무서|걱정)"
            r"|손해[^?]{0,12}(?:나면|났|어떡|무서|걱정)"
            r"|돈[^?]{0,8}(?:잃|까먹)"
            r"|원금[^?]{0,10}(?:까먹|잃|날리)"
            r"|투자(?:가|는)?[^?]{0,8}(?:무서|겁나|두려)"
            r"|무서(?:워|운|위)|겁나|두려[워운]"
            r"|다\s*잃",
            re.I,
        ),
    ),
)


def _hesitation_answer_id(message: str) -> str | None:
    """Identify a hesitation question so it gets facts instead of a dead end."""

    for answer_id, pattern in _HESITATION_PATTERNS:
        if pattern.search(message) is not None:
            return answer_id
    return None


# 특정 금융회사를 고르는 질문. 회사를 권유하지 않고 비교 기준을 제시한다.
_PROVIDER_CHOICE_ADVICE = re.compile(
    r"(?:증권사|은행|보험사|금융\s*회사)[^?]{0,14}"
    r"(?:어디|어느|중에).{0,12}(?:나은|나아|좋|괜찮|해야)"
    r"|(?:어디|어느)[^?]{0,12}(?:에서|로)?\s*"
    r"(?:만들|가입|개설).{0,12}(?:좋|나은|나아|괜찮|될까|할까)"
    r"|(?:증권사|은행|보험사)[^?]{0,10}추천",
    re.I,
)
# "나 어떻게 투자해야 해?"처럼 조건 없이 개인 맞춤 답을 구하는 질문.
# 상품을 고르는 대신 필요한 조건을 되묻고 성향별 비교로 잇는다.
_PERSONAL_ALLOCATION_ADVICE = re.compile(
    r"(?:나|내가|저).{0,8}(?:어떻게|뭘|무엇을).{0,10}(?:투자|운용|사|해야|담)"
    r"|어떻게\s*(?:투자|운용)(?:해야|하면|할까|하지)"
    r"|(?:뭐|무엇|어떤\s*거).{0,6}(?:사|담|골라|넣)(?:야|아야|어야|면)?\s*"
    r"(?:돼|되|할까|좋을까|하지)"
    r"|내\s*나이.{0,10}(?:뭐|무엇|어떤).{0,8}(?:맞|좋)"
    r"|(?:수익률|수익).{0,8}(?:높은|좋은).{0,8}(?:거|것|상품|알려|추천)"
    r"|(?:ETF|상품|펀드|종목)[^?]{0,10}(?:제일|가장)[^?]{0,6}(?:좋|나은)"
    r"|(?:제일|가장)[^?]{0,6}(?:좋|나은)[^?]{0,10}(?:ETF|상품|펀드|종목)"
    r"|(?:지금|오늘|이제)[^?]{0,8}"
    r"(?:사|팔|팔아|파|매수|매도)[^?]{0,8}(?:될까|돼|되나|해야|할까|하나|해)",
    re.I,
)
# 원금 보장·손실 회피를 구하는 질문. 안심시키지 않고 제도 사실로 돌린다.
_PRINCIPAL_GUARANTEE_QUESTION = re.compile(
    r"원금.{0,8}(?:보장|지키|잃)"
    r"|손해.{0,10}안\s*(?:보|나)"
    r"|손실.{0,10}(?:없|안\s*(?:나|보))"
    r"|안전한\s*(?:상품|거|것)"
    r"|(?:얼마나|얼마).{0,8}(?:벌|수익).{0,8}(?:수\s*있|나|될까)"
    r"|(?:사면|하면).{0,8}돈.{0,6}(?:벌|되)",
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
_PORTFOLIO_STRATEGY_LABEL = re.compile(
    r"(?:자본\s*보전\s*중심|방어적\s*분산|"
    r"(?:성장\s*)?코어\s*[·ㆍ\-\s]?\s*위성|"
    r"바벨형\s*성장\s*[·ㆍ\-\s]?\s*전술)\s*전략"
)
_STRATEGY_RATIONALE_QUESTION = re.compile(
    r"왜|이유|근거|선택|적합|맞(?:아|는|나요)"
)
# 리밸런싱을 "언제·얼마나 자주" 하는지는 성향별 점검 주기가 답이다.
# 엔진이 이미 성향마다 주기를 계산하므로 안내 경로로 잇는다.
_REBALANCING_CADENCE_QUESTION = re.compile(
    r"(?:리\s*밸런싱|리밸런스)[^?]{0,12}"
    r"(?:언제|얼마나\s*자주|주기|자주\s*해|몇\s*(?:개월|달|번))"
    r"|(?:언제|얼마나\s*자주|주기)[^?]{0,12}(?:리\s*밸런싱|리밸런스)"
)
# 화면의 "챗봇에 점검 요청" 버튼이 보내는 문장. 보유내역 첨부가 없어도
# 같은 말을 직접 입력하면 전략 안내로 잇는다.
_REBALANCING_REVIEW_REQUEST = re.compile(
    r"(?:리\s*밸런싱|리밸런스|비중|자산\s*배분)[^?]{0,12}"
    r"(?:점검|검토|확인)"
    r"|(?:점검|검토)[^?]{0,12}(?:리\s*밸런싱|리밸런스)"
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
    # 구어 표기를 표준형으로 접은 뒤 분류한다. "연금이 머야"를 미분류로 흘리면
    # 문맥 보정이 엉뚱한 인텐트로 승격시키기 때문이다. 차단 규칙도 같은 표준형을
    # 보므로 표기를 바꿔 가드를 우회할 수 없다.
    normalized = normalize_colloquial_text(message)
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
    named_portfolio_strategy = (
        _PORTFOLIO_STRATEGY_LABEL.search(normalized) is not None
    )
    requests_strategy_rationale = (
        named_portfolio_strategy
        and _STRATEGY_RATIONALE_QUESTION.search(normalized) is not None
    )
    if (
        named_portfolio_strategy
        and "테마" not in normalized
        and _PRODUCT_LOOKUP_CONTEXT.search(normalized) is None
    ):
        # "코어·위성 전략"의 위성은 포트폴리오 역할을 뜻한다. 방산·우주
        # 테마의 별칭으로 먼저 해석하면 직전 전략 설명이 엉뚱한 ETF 답변으로 샌다.
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
            or named_portfolio_strategy
            or _AGE_BASED_ALLOCATION_QUESTION.search(normalized) is not None
            or _REBALANCING_CADENCE_QUESTION.search(normalized) is not None
            or _REBALANCING_REVIEW_REQUEST.search(normalized) is not None
        ),
        ChatIntent.PROVIDER_DISCLOSURE: bool(account_types)
        and _DISCLOSURE_TERMS.search(normalized) is not None,
        ChatIntent.ACCOUNT_RULE: bool(
            requests_pension_planner
            or account_types
            or account_rule_topic
            or (_PENSION_CONTEXT.search(normalized) and _RULE_TERMS.search(normalized))
            or _PENSION_PRACTICE_QUESTION.search(normalized) is not None
        ),
    }
    personal_account_tax_request = (
        intent_matches[ChatIntent.PENSION_TAX]
        and re.search(r"내\s*계좌", normalized) is not None
    )
    # 정답이 사람마다 다른 조언형 질문은 금액·회사를 고르지 않고, 공식
    # 기준점과 비교 항목을 제시하는 대안 응답으로 돌린다. 다른 인텐트가
    # 이미 구체적으로 잡은 질문은 건드리지 않는다.
    # 금융회사 선택은 "은행" 같은 말이 테마명과 겹치므로 테마 매칭보다 앞선다.
    advice_candidate = not any(
        matched
        for candidate, matched in intent_matches.items()
        if candidate is not ChatIntent.ETF_THEME
    )
    if advice_candidate:
        if _CONTRIBUTION_AMOUNT_ADVICE.search(normalized):
            return _blocked(
                normalized,
                BlockedReason.CONTRIBUTION_AMOUNT_ADVICE,
                max_results,
            )
        if _PROVIDER_CHOICE_ADVICE.search(normalized):
            return _blocked(
                normalized,
                BlockedReason.PROVIDER_CHOICE_ADVICE,
                max_results,
            )
        advice_scope = _NON_PENSION_ASSET.search(normalized) is None
        if advice_scope and _PRINCIPAL_GUARANTEE_QUESTION.search(normalized):
            return _blocked(
                normalized,
                BlockedReason.PRINCIPAL_GUARANTEE_QUESTION,
                max_results,
            )
        if advice_scope and _PERSONAL_ALLOCATION_ADVICE.search(normalized):
            return _blocked(
                normalized,
                BlockedReason.PERSONAL_ALLOCATION_ADVICE,
                max_results,
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
    # 정의를 묻는 것이 분명하고 사전에 있는 용어라면 데이터 조회보다 뜻풀이가
    # 먼저다. "채권이 뭐야?"에 ETF 카탈로그를, "인플레이션이 뭐야?"에 거시지표
    # 수치를 주면 질문·답변이 어긋난다. 계좌·세액 인텐트는 제도 설명이 더
    # 정확하므로 그대로 둔다.
    # 단, "반도체 ETF가 뭐야?"처럼 상품을 함께 지목한 질문은 카탈로그 안내가
    # 답이므로 양보하지 않는다.
    if (
        intent in _DEFINITION_OVERRIDABLE_INTENTS
        and _PRODUCT_LOOKUP_CONTEXT.search(normalized) is None
        and _DEFINITION_QUESTION.search(normalized)
    ):
        definition_term_id = _glossary_term_id(normalized)
        if definition_term_id is not None:
            return QueryPlan(
                normalized_message=normalized,
                intent=ChatIntent.GLOSSARY,
                max_results=max_results,
                glossary_term_id=definition_term_id,
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
            requests_strategy_rationale=requests_strategy_rationale,
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
    # "왜 그렇게 하나"는 뜻풀이로 답이 되지 않으므로 용어보다 먼저 본다.
    # "리밸런싱이 뭐야?"는 용어, "리밸런싱을 왜 해?"는 원리다.
    investing_principle_id = _investing_principle_id(normalized)
    if investing_principle_id is not None:
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.INVESTING_PRINCIPLE,
            max_results=max_results,
            investing_principle_id=investing_principle_id,
        )
    # 망설임이 담긴 질문은 안전 폴백으로 떨어뜨리지 않고 사실로 답한다.
    # 연금 밖 자산을 지목한 질문은 기존 폴백을 유지한다.
    if _NON_PENSION_ASSET.search(normalized) is None:
        hesitation_answer_id = _hesitation_answer_id(normalized)
        if hesitation_answer_id is not None:
            return QueryPlan(
                normalized_message=normalized,
                intent=ChatIntent.HESITATION_SUPPORT,
                max_results=max_results,
                hesitation_answer_id=hesitation_answer_id,
            )
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
    # 어느 계좌·상품 비용인지 없는 금액 질문은 숫자를 추정하지 않고, 사용자가
    # 비교 대상을 고를 수 있도록 되묻는다. 구체적인 계좌·상품·공시 질문은 위의
    # 기존 인텐트가 먼저 처리한다.
    if _FEE_TARGET_REQUIRED.search(normalized):
        return _blocked(
            normalized,
            BlockedReason.FEE_TARGET_REQUIRED,
            max_results,
        )
    return _blocked(normalized, BlockedReason.UNSUPPORTED, max_results)
