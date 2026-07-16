_KIWOOM_TDF_SOURCE = (
    "https://www.kiwoometf.com/service/invest/"
    "KO04020102T?kijaGubun=10&kijaNo=314"
)
_KODEX_TDF_SOURCE = (
    "https://m.samsungfund.com/upload/kodex/newsroom/"
    "20241202171319440.pdf"
)


ETF_DISCLOSURE_OVERRIDES: dict[str, dict[str, object]] = {
    "0025N0": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_product_disclosure",
        "source_title": "TIGER TDF2045 적격 상품정보",
        "source_url": (
            "https://www.tigeretf.com/ko/product/search/detail/"
            "index.do?ksdFund=KR70025N0008"
        ),
        "basis": "해외 주식 슬리브의 환헤지를 실시하지 않는 환노출 구조",
    },
    "433880": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_investment_prospectus",
        "source_title": "PLUS 적격TDF2060액티브 투자설명서",
        "source_url": (
            "https://www.plusetf.co.kr/upload/fund/"
            "J260411402투자설명서-한화%20PLUS%20적격TDF2060액티브"
            "증권상장지수투자신탁(주식혼합-재간접형)-006357-20260401.pdf"
        ),
        "basis": "투자설명서가 환헤지를 실행하지 않을 계획임을 명시",
    },
    "433970": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_retirement_guide",
        "source_title": "Kodex 연금투자 가이드북",
        "source_url": _KODEX_TDF_SOURCE,
        "basis": "TDF2030 환헤지 미실시 및 환율 변동 노출 명시",
    },
    "433980": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_retirement_guide",
        "source_title": "Kodex 연금투자 가이드북",
        "source_url": _KODEX_TDF_SOURCE,
        "basis": "동일 TDF 액티브 시리즈의 환헤지 미실시 정책 명시",
    },
    "434060": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_retirement_guide",
        "source_title": "Kodex 연금투자 가이드북",
        "source_url": _KODEX_TDF_SOURCE,
        "basis": "TDF2050 환헤지 미실시 및 환율 변동 노출 명시",
    },
    "435530": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_product_research",
        "source_title": "KIWOOM TDF 액티브 ETF 상품 설명",
        "source_url": _KIWOOM_TDF_SOURCE,
        "basis": (
            "TDF2030·2040·2050 ETF가 환노출형이며 원칙적으로 "
            "환헤지하지 않음을 명시"
        ),
    },
    "435540": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_product_research",
        "source_title": "KIWOOM TDF 액티브 ETF 상품 설명",
        "source_url": _KIWOOM_TDF_SOURCE,
        "basis": (
            "TDF2030·2040·2050 ETF가 환노출형이며 원칙적으로 "
            "환헤지하지 않음을 명시"
        ),
    },
    "435550": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_product_research",
        "source_title": "KIWOOM TDF 액티브 ETF 상품 설명",
        "source_url": _KIWOOM_TDF_SOURCE,
        "basis": (
            "TDF2030·2040·2050 ETF가 환노출형이며 원칙적으로 "
            "환헤지하지 않음을 명시"
        ),
    },
    "440340": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "investment_prospectus",
        "source_title": "TIGER 글로벌멀티에셋TIF액티브 간이투자설명서",
        "source_url": (
            "https://image.kebhana.com/cont/download/pensionETF/"
            "W41A440340_investbrief.pdf"
        ),
        "basis": "환율변동위험 제거를 위한 환헤지 전략을 실행하지 않음을 명시",
    },
    "442550": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_investment_prospectus",
        "source_title": "RISE 적격TDF2030액티브 간이투자설명서",
        "source_url": (
            "https://www.riseetf.co.kr/upload/cdn/2026/04/03/"
            "202604036acf78197b84491.pdf"
        ),
        "basis": "비교지수를 원화환산지수(환헤지 안함)로 명시",
    },
    "442560": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_investment_prospectus",
        "source_title": "RISE 적격TDF2040액티브 간이투자설명서",
        "source_url": (
            "https://www.riseetf.co.kr/upload/cdn/2026/04/03/"
            "20260403375ee7d4d6a1450.pdf"
        ),
        "basis": "비교지수를 원화환산지수(환헤지 안함)로 명시",
    },
    "442570": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_investment_prospectus",
        "source_title": "RISE 적격TDF2050액티브 간이투자설명서",
        "source_url": (
            "https://www.riseetf.co.kr/upload/cdn/2026/04/03/"
            "20260403cfb4febe4c1e499.pdf"
        ),
        "basis": "비교지수를 원화환산지수(환헤지 안함)로 명시",
    },
    "461490": {
        "currency_hedge": "unhedged",
        "confidence": "high",
        "verified_as_of": "2026-07-15",
        "source_type": "issuer_investment_prospectus",
        "source_title": "RISE 글로벌자산배분액티브 투자설명서",
        "source_url": (
            "https://www.riseetf.co.kr/upload/cdn/2026/01/29/"
            "2026012938bdc5b1f8f54ac.pdf"
        ),
        "basis": "별도의 환헤지 전략을 실시하지 않을 계획임을 명시",
    },
}
