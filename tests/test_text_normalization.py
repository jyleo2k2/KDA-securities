"""구어 표기 정규화의 미탐·오탐을 함께 고정한다.
정규식으로 표기를 접는 방식은 정상 단어를 잘못 건드리기 쉽다. 그래서 접어야
하는 표기와 절대 건드리면 안 되는 문장을 같은 파일에서 검증한다.
"""

import pytest

from backend.app.text_normalization import (
    normalize_colloquial_text,
    normalize_search_text,
)

# 접어야 하는 구어 표기. 왼쪽을 정규화하면 오른쪽이 되어야 한다.
FOLDED_CASES = (
    ("연금이 머야", "연금이 뭐야"),
    ("연금이 모야", "연금이 뭐야"),
    ("ETF가 머야", "ETF가 뭐야"),
    ("리밸런싱이 머야", "리밸런싱이 뭐야"),
    ("IRP가 머임", "IRP가 뭐임"),
    ("연금저축이 머냐", "연금저축이 뭐냐"),
    ("TDF가 머예요", "TDF가 뭐예요"),
    ("디폴트옵션이 모에요", "디폴트옵션이 뭐에요"),
    ("연금이 머지", "연금이 뭐지"),
    ("세액공제가 머인지", "세액공제가 뭐인지"),
    ("연금이 뭐에여", "연금이 뭐예요"),
)

# 건드리면 안 되는 문장. "머"·"모"로 시작하는 정상 단어가 들어 있다.
PRESERVED_CASES = (
    "머리가 아파요",
    "모임에서 들었는데 연금저축이 좋대",
    "모아둔 돈으로 뭘 사야 해",
    "머니마켓펀드가 뭐야",
    "목돈을 모으려면 어떻게 해",
    "연금 모으는 방법 알려줘",
    "머무는 기간이 길수록 유리한가요",
)


@pytest.mark.parametrize(("spoken", "standard"), FOLDED_CASES)
def test_colloquial_spelling_is_folded(spoken: str, standard: str) -> None:
    assert normalize_colloquial_text(spoken) == standard


@pytest.mark.parametrize("message", PRESERVED_CASES)
def test_ordinary_words_are_preserved(message: str) -> None:
    assert normalize_colloquial_text(message) == normalize_search_text(message)


def test_standard_spelling_is_unchanged() -> None:
    for message in ("연금이 뭐야", "ETF가 무엇인가요", "연금저축이 뭔데"):
        assert normalize_colloquial_text(message) == message


def test_search_normalization_keeps_original_spelling() -> None:
    """검색·수집 경로는 구어 표기를 접지 않는다."""

    assert normalize_search_text("연금이 머야") == "연금이 머야"


def test_blank_input_is_handled() -> None:
    assert normalize_colloquial_text("   ") == ""
