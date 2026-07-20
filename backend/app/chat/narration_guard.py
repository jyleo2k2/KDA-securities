"""Deterministic narration guards for verified chatbot responses."""

import re
from decimal import Decimal, InvalidOperation

_ARABIC_NUMBER = re.compile(
    r"(?<![0-9A-Za-z_])(?P<sign>[+\-−])?"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    # 긴 통화 단위를 먼저 둬 '3조원'이 '3조'로 잘리지 않게 한다. 세·주·위·
    # 조·평·원은 값이 같아도 의미가 달라 단위 스왑을 보수적으로 거부한다.
    r"(?P<unit>조\s*원|백\s*만\s*원|천\s*만\s*원|억\s*원|만\s*원|"
    r"천\s*원|원|KRW|퍼센트|프로|%|년|개월|월|분기|일|세|주|위|"
    r"조|평|배|개|건|명|회|차|층)?"
    r"(?![0-9A-Za-z_])",
    re.I,
)
_LEGAL_FRACTION = re.compile(
    r"(?P<denominator>\d[\d,]*)\s*분의\s*(?P<numerator>\d[\d,]*(?:\.\d+)?)"
)
_PERCENT_RANGE = re.compile(
    r"(?<!\d)(?P<left>\d[\d,]*(?:\.\d+)?)\s*%?\s*"
    r"(?:~|〜|–|—)\s*(?P<right>\d[\d,]*(?:\.\d+)?)\s*%(?!\d)"
)
_ISO_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})(?!\d)"
)
_KOREAN_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{4})\s*년\s*(?P<month>\d{1,2})\s*월\s*"
    r"(?P<day>\d{1,2})\s*일(?!\d)"
)
_DOTTED_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{4})\.(?P<month>\d{1,2})\.(?P<day>\d{1,2})(?!\d)"
)
_CURRENCY_MULTIPLIERS = {
    "원": Decimal("1"),
    "천원": Decimal("1000"),
    "만원": Decimal("10000"),
    "백만원": Decimal("1000000"),
    "천만원": Decimal("10000000"),
    "억원": Decimal("100000000"),
    "조원": Decimal("1000000000000"),
    "krw": Decimal("1"),
}
_KOREAN_NUMBER = re.compile(
    # '3천만 원'의 '천만 원'을 별도 한글 숫자로 중복 추출하지 않는다.
    r"(?<![0-9A-Za-z_,하나다섯여섯일곱여덟아홉영공일이삼사오육칠팔구십백천만억한두둘세셋네넷열])"
    r"(?P<sign>마이너스|플러스)?\s*"
    r"(?P<number>(?:하나|다섯|여섯|일곱|여덟|아홉|영|공|일|이|삼|"
    r"사|오|육|칠|팔|구|십|백|천|만|억|한|두|둘|세|셋|네|넷|열)+)\s*"
    r"(?P<unit>퍼센트|프로|백\s*만\s*원|천\s*만\s*원|억\s*원|"
    r"만\s*원|천\s*원|원|년|개월|배|개|건|명|회|번|계좌)"
)
_KOREAN_DIGITS = {
    "영": 0,
    "공": 0,
    "한": 1,
    "하나": 1,
    "일": 1,
    "두": 2,
    "둘": 2,
    "이": 2,
    "세": 3,
    "셋": 3,
    "삼": 3,
    "네": 4,
    "넷": 4,
    "사": 4,
    "오": 5,
    "다섯": 5,
    "육": 6,
    "여섯": 6,
    "칠": 7,
    "일곱": 7,
    "팔": 8,
    "여덟": 8,
    "구": 9,
}
_KOREAN_SMALL_UNITS = {"십": 10, "백": 100, "천": 1000}
_KOREAN_LARGE_UNITS = {"만": 10_000, "억": 100_000_000}
_KOREAN_NUMBER_WORDS = tuple(
    sorted(
        (*_KOREAN_DIGITS, *_KOREAN_SMALL_UNITS, *_KOREAN_LARGE_UNITS, "열"),
        key=len,
        reverse=True,
    )
)
_UNSAFE_CLAIM_PATTERNS = (
    (
        "future_outlook",
        re.compile(
            r"(?:앞으로|향후|내년|미래|다음\s*분기).{0,30}"
            r"(?:수익(?:률)?|가격|주가).{0,20}"
            r"(?:오르|상승|하락|내리|증가|감소|전망|예상)"
            r"|(?:수익(?:률)?|가격|주가).{0,20}"
            r"(?:앞으로|향후|내년|미래).{0,20}"
            r"(?:오르|상승|하락|내리|증가|감소)"
            r"|(?:수익(?:률)?|가격|주가).{0,12}"
            r"(?:오를|내릴|상승할|하락할|증가할|감소할|전망|예상)"
        ),
    ),
    (
        "guarantee",
        re.compile(
            r"(?:\d[\d,.]*\s*(?:%|퍼센트|프로)|%|퍼센트|프로|"
            # 수익·원금·손실 뒤의 수식어는 길어도 40자까지만 위험 주장으로 묶는다.
            r"수익(?:률)?|원금|손실).{0,40}(?:보장|확정|확실)"
            r"|원금.{0,15}(?:줄지\s*않|감소하지\s*않|손실이\s*없)"
        ),
    ),
    (
        "recommendation",
        re.compile(
            r"(?:매수|매도|상품|투자).{0,20}(?:추천|권유)"
            r"|(?:추천|권유).{0,20}(?:매수|매도|상품|투자)"
            r"|(?:매수|매도).{0,15}(?:좋|유리)"
            r"|(?:사는|파는)\s*게\s*(?:좋|유리)"
            r"|(?:사세요|파세요|매수하세요|매도하세요|투자하세요)"
            # '담으시면 돼요'처럼 매수·추천 어휘를 생략한 직접 권유도 차단한다.
            r"|(?:담으시면|고르시는\s*게|선택하시는\s*게).{0,10}"
            r"(?:돼|좋|낫|유리)"
        ),
    ),
)
# 위험 주장 앞의 '손실 없이', '예금이 아니라'는 뒤 주장을 부정하지 않는다.
# 따라서 매치 주변 창이 아니라 주장 키워드 직후의 문법적 꼬리만 부정으로
# 인정한다. 애매한 원거리 부정은 안전 우선으로 거부(결정론 폴백)한다.
_NEGATION = re.compile(
    r"^\s*(?:은|는|이|가|을|를|도)?\s*"
    r"(?:하(?:지\s*(?:않|못)|지\s*마)|"
    # '보장되는 상품이 아니다'처럼 보장 여부를 직접 부정한 형태만 허용한다.
    r"되(?:\s*지\s*(?:않|못)|는\s*상품이\s*아니)|"
    r"할\s*수\s*없|(?:해서는|하면|해도)\s*안\s*(?:돼|되)|"
    r"안\s*(?:돼|되)|허용되지|금지|아니|없|못|제공하지|의미하지)"
)
_DOUBLE_NEGATION_TAIL = re.compile(r"^\s*(?:는|은)?\s*게\s*아니라")


def _number_tokens(text: str) -> set[tuple[Decimal, str, str]]:
    values: set[tuple[Decimal, str, str]] = set()
    # 법령 원문은 비율을 "100분의 15"로 쓰고 내레이터는 "15%"로 재서술한다.
    # 같은 수치이므로 같은 토큰으로 맞춘다. 구성 숫자(100·15)를 따로 남기면
    # 재서술이 그 숫자를 안 써서 오히려 어긋나므로 원 표기는 걷어낸다.
    for match in _LEGAL_FRACTION.finditer(text):
        denominator = Decimal(match.group("denominator").replace(",", ""))
        numerator = Decimal(match.group("numerator").replace(",", ""))
        if denominator:
            values.add((numerator / denominator * 100, "%", "unsigned"))

    # '10~20%'와 '10%~20%'는 양 끝이 모두 퍼센트인 같은 범위다. 명시적인
    # % 종결 범위만 정규화하며 단위 없는 일반 범위는 추론하지 않는다.
    for match in _PERCENT_RANGE.finditer(text):
        left = Decimal(match.group("left").replace(",", ""))
        right = Decimal(match.group("right").replace(",", ""))
        values.update({(left, "%", "unsigned"), (right, "%", "unsigned")})

    # ISO·한국어·점 날짜 표기만 연·월·일 토큰으로 맞춘다. 달력값을 다른
    # 단위로 바꾸지 않아 날짜가 아닌 숫자를 동치로 오인하지 않는다.
    for date_pattern in (_ISO_DATE, _KOREAN_DATE, _DOTTED_DATE):
        for match in date_pattern.finditer(text):
            values.update(
                {
                    (Decimal(match.group("year")), "date_year", "unsigned"),
                    (Decimal(match.group("month")), "date_month", "unsigned"),
                    (Decimal(match.group("day")), "date_day", "unsigned"),
                }
            )

    remaining = _LEGAL_FRACTION.sub(" ", text)
    remaining = _PERCENT_RANGE.sub(" ", remaining)
    remaining = _ISO_DATE.sub(" ", remaining)
    remaining = _KOREAN_DATE.sub(" ", remaining)
    remaining = _DOTTED_DATE.sub(" ", remaining)
    for match in _ARABIC_NUMBER.finditer(remaining):
        raw_sign = match.group("sign")
        sign = "-" if raw_sign in {"-", "−"} else ""
        sign_kind = (
            "negative"
            if raw_sign in {"-", "−"}
            else "positive"
            if raw_sign == "+"
            else "unsigned"
        )
        try:
            value = Decimal(sign + match.group("number").replace(",", ""))
        except InvalidOperation:
            continue
        unit = re.sub(r"\s+", "", match.group("unit") or "number").casefold()
        multiplier = _CURRENCY_MULTIPLIERS.get(unit)
        if multiplier is not None:
            value *= multiplier
            unit = "krw"
        values.add((value, unit, sign_kind))
    return values


# 한 글자 숫자어(이·한·일·구·사·오·공·영)는 흔한 낱말의 첫 글자와 겹쳐
# (이번·이건·한번·구원·사실·오늘) regex가 형태소 경계 없이 숫자로 오인한다.
# 이런 단독 한 글자 모호 숫자어는 숫자 토큰에서 제외한다. 두 글자 이상 조합
# (칠십·구백만)은 일상어와 겹치지 않아 그대로 검증하고, 실제 조작 수치는
# 아라비아 숫자 가드(_ARABIC_NUMBER)가 엄격히 잡는다.
_AMBIGUOUS_SINGLE_KOREAN_NUMERALS = frozenset("이한일구사오공영")
_APPROXIMATE_COUNT_NUMERALS = frozenset({"한두", "두세"})
_NON_NUMERIC_KOREAN_COMPOUNDS = frozenset({"이사회", "육회"})
_IDIOMATIC_HUNDRED_TIMES_SUFFIX = re.compile(r"^\s*(?:맞|옳)(?:는|은)?\s*말")


def _is_non_numeric_korean_match(
    text: str,
    match: re.Match[str],
    *,
    number: str,
    unit: str,
) -> bool:
    """Exclude only narrow, explainable Korean homographs from number tokens."""

    raw = match.group()
    if raw in _NON_NUMERIC_KOREAN_COMPOUNDS:
        return True
    if unit == "번" and number in _APPROXIMATE_COUNT_NUMERALS:
        # 한두/두세 번은 정확값이 아닌 일상 어림수라 검증 수치로 연결하지 않는다.
        return True
    compact = re.sub(r"\s+", "", raw)
    # '백번 맞는 말'에서 백번은 횟수 주장이 아니라 강조 관용구다.
    return compact == "백번" and bool(
        _IDIOMATIC_HUNDRED_TIMES_SUFFIX.search(text[match.end() :])
    )


def _parse_korean_number(number: str) -> Decimal:
    """Parse the exact Korean numeral forms accepted by _KOREAN_NUMBER."""

    total = 0
    group = 0
    pending_digit: int | None = None
    index = 0
    while index < len(number):
        word = next(
            (word for word in _KOREAN_NUMBER_WORDS if number.startswith(word, index)),
            None,
        )
        if word is None:
            raise ValueError(f"unsupported Korean numeral: {number}")
        index += len(word)
        if word == "열":
            group += 10
        elif word in _KOREAN_DIGITS:
            pending_digit = _KOREAN_DIGITS[word]
        elif word in _KOREAN_SMALL_UNITS:
            group += (pending_digit if pending_digit is not None else 1) * (
                _KOREAN_SMALL_UNITS[word]
            )
            pending_digit = None
        else:
            group += pending_digit or 0
            total += (group or 1) * _KOREAN_LARGE_UNITS[word]
            group = 0
            pending_digit = None
    return Decimal(total + group + (pending_digit or 0))


def _korean_number_tokens(text: str) -> set[tuple[Decimal, str, str]]:
    values: set[tuple[Decimal, str, str]] = set()
    for match in _KOREAN_NUMBER.finditer(text):
        number = re.sub(r"\s+", "", match.group("number"))
        if number in _AMBIGUOUS_SINGLE_KOREAN_NUMERALS:
            continue
        sign = match.group("sign") or ""
        unit = re.sub(r"\s+", "", match.group("unit"))
        if _is_non_numeric_korean_match(
            text,
            match,
            number=number,
            unit=unit,
        ):
            continue
        value = _parse_korean_number(number)
        sign_kind = (
            "negative"
            if sign == "마이너스"
            else "positive"
            if sign == "플러스"
            else "unsigned"
        )
        if sign_kind == "negative":
            value = -value
        unit = {"퍼센트": "%", "프로": "%"}.get(unit, unit)
        multiplier = _CURRENCY_MULTIPLIERS.get(unit)
        if multiplier is not None:
            value *= multiplier
            unit = "krw"
        values.add((value, unit, sign_kind))
    return values


def _unsafe_claim_instances(text: str) -> set[tuple[str, str]]:
    """Return each non-negated claim as category plus normalized matched text.

    카테고리만 비교하면 원문의 '원금 보장' 하나로 새 '수익 보장'까지 통과한다.
    공백·문장부호만 제거한 실제 매치 문구를 함께 비교해 그 우회를 막는다.
    """

    claims: set[tuple[str, str]] = set()
    for category, pattern in _UNSAFE_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            suffix = text[match.end() : match.end() + 24]
            negation = _NEGATION.search(suffix)
            # '보장되지 않는 게 아니라 보장됩니다'는 이중부정으로 결국 보장
            # 주장이다. 직접 부정 다음의 '게 아니라'만 좁게 예외 처리한다.
            if negation is None or _DOUBLE_NEGATION_TAIL.search(
                suffix[negation.end() :]
            ):
                normalized_match = re.sub(
                    r"[^0-9A-Za-z가-힣%]+", "", match.group()
                ).casefold()
                claims.add((category, normalized_match))
    return claims


def _unsafe_claims(text: str) -> set[str]:
    return {category for category, _ in _unsafe_claim_instances(text)}


def contains_unsafe_financial_claim(text: str) -> bool:
    """Expose the narrator's positive-claim guard to verified RAG consumers."""

    return bool(_unsafe_claim_instances(text))


def _adds_unverified_content(candidate: str, source: str) -> bool:
    candidate_numbers = _number_tokens(candidate) | _korean_number_tokens(candidate)
    source_numbers = _number_tokens(source) | _korean_number_tokens(source)
    return (
        not candidate_numbers.issubset(source_numbers)
        or not _unsafe_claim_instances(candidate).issubset(
            _unsafe_claim_instances(source)
        )
    )
