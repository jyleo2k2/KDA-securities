from backend.app.chat.etf_product_features import (
    ClaudeEtfProductFeatureGenerator,
    EtfProductFeatureBatch,
    EtfProductFeatureFacts,
    EtfProductFeatureResult,
    deterministic_etf_product_feature,
)


def _facts() -> EtfProductFeatureFacts:
    return EtfProductFeatureFacts(
        isu_code="487240",
        product_name="KODEX AI전력핵심설비",
        theme_name="AI·소프트웨어",
        benchmark_name="iSelect AI 전력핵심설비 지수(Price Return)",
        classification={"asset_class": "equity", "region": "south_korea"},
        top_holding_names=("효성중공업", "HD현대일렉트릭", "LS ELECTRIC"),
    )


def test_deterministic_feature_uses_benchmark_and_kis_holdings() -> None:
    feature = deterministic_etf_product_feature(_facts())

    assert "iSelect AI 전력핵심설비 지수" in feature
    assert "효성중공업·HD현대일렉트릭·LS ELECTRIC" in feature
    assert "상품 설명 확인 필요" not in feature


def test_generated_feature_requires_verbatim_support_from_merged_markdown() -> None:
    generator = ClaudeEtfProductFeatureGenerator.__new__(
        ClaudeEtfProductFeatureGenerator
    )
    generator._research_text = generator._research_path = None
    generator._research_text = (
        "## [ETF:487240] KODEX AI전력핵심설비\n\n"
        "- 상품 설명: 국내 전력기기 대표 기업과 변압기·전선·구리 "
        "밸류체인에 투자합니다."
    )
    facts = _facts()
    output = EtfProductFeatureBatch(
        products=(
            EtfProductFeatureResult(
                isu_code="487240",
                feature=(
                    "국내 전력기기와 변압기·전선·구리 밸류체인에 "
                    "투자합니다."
                ),
                support_quote=(
                    "국내 전력기기 대표 기업과 변압기·전선·구리 "
                    "밸류체인에 투자합니다."
                ),
            ),
        )
    )

    assert generator._validate(output, (facts,)) == {
        "487240": "국내 전력기기와 변압기·전선·구리 밸류체인에 투자합니다."
    }


def test_generated_feature_rejects_fee_or_trading_value_repetition() -> None:
    generator = ClaudeEtfProductFeatureGenerator.__new__(
        ClaudeEtfProductFeatureGenerator
    )
    generator._research_text = (
        "## [ETF:487240] KODEX AI전력핵심설비\n\n"
        "- 상품 설명: 국내 전력기기 기업에 투자합니다."
    )
    facts = _facts()
    output = EtfProductFeatureBatch(
        products=(
            EtfProductFeatureResult(
                isu_code="487240",
                feature="총보수와 거래대금이 낮은 상품입니다.",
                support_quote="국내 전력기기 기업에 투자합니다.",
            ),
        )
    )

    assert generator._validate(output, (facts,)) == {}
