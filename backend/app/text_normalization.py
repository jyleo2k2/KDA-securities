import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_search_text(value: str) -> str:
    """Return a stable display-and-storage form for user search text."""

    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()


# 구어 표기를 표준형으로 접는다. "연금이 머야"처럼 인터넷에서 흔히 쓰는 말을
# 의도 분류기가 알아듣게 하는 것이 목적이다.
#
# 주의: 아래 치환은 의도 분류에만 쓴다. 뉴스 수집·RAG 검색은
# ``normalize_search_text``를 그대로 사용해야 원문 질의가 보존된다.
# "머리"·"모임"처럼 정상 단어의 첫 글자를 건드리면 안 되므로, 의문사로 쓰인
# 자리에만 매칭되도록 앞뒤 경계를 함께 요구한다.

# 의문사 "뭐"의 구어 표기. 앞은 문장 시작이나 조사·공백, 뒤는 의문 종결이라야
# 한다. 이 경계 때문에 "머리가 아파"의 "머"는 매칭되지 않는다.
_COLLOQUIAL_WHAT = re.compile(
    r"(?<![가-힣])[머모](?=(?:야|여|에요|예요|에여|얘요|임|인가|인지|냐|니|지)\b)"
)
# 종결만 구어인 경우. "뭐에여"·"뭐래요"처럼 앞 글자는 이미 표준형이다.
_COLLOQUIAL_ENDING = re.compile(r"(?<=뭐)(?:에여|예여|에염|이에염)\b")
# 자음만 남긴 축약. "ㅁㅇ"는 뜻이 갈리므로 다루지 않고, 널리 쓰이는 형태만 편다.
_COLLOQUIAL_CONTRACTION = (
    ("뭔뎅", "뭔데"),
    ("머임", "뭐임"),
    ("모임니까", "뭡니까"),
)


def normalize_colloquial_text(value: str) -> str:
    """Fold common Korean internet spellings into their standard question form.

    Intended for intent classification only. The returned text is never shown to
    the user and never used as a search query.
    """

    normalized = normalize_search_text(value)
    if not normalized:
        return normalized
    normalized = _COLLOQUIAL_WHAT.sub("뭐", normalized)
    normalized = _COLLOQUIAL_ENDING.sub("예요", normalized)
    for spoken, standard in _COLLOQUIAL_CONTRACTION:
        normalized = normalized.replace(spoken, standard)
    return normalized
