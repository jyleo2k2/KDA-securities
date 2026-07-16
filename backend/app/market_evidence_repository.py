import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .engine.market_evidence import KrxEtfEvidenceProduct


class KrxMarketEvidenceReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    report_type: str
    as_of: date
    product_count: int = Field(ge=1)
    current_listed_universe_count: int = Field(ge=1)
    excluded_insufficient_observations_count: int = Field(ge=0)
    excluded_not_currently_listed_count: int = Field(ge=0)
    minimum_candidate_observations: int = Field(ge=253)
    products: list[KrxEtfEvidenceProduct] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_report_contract(self) -> "KrxMarketEvidenceReport":
        if self.product_count != len(self.products):
            raise ValueError("KRX report product_count does not match products")
        codes = [product.isu_code for product in self.products]
        if len(codes) != len(set(codes)):
            raise ValueError("KRX report contains duplicate ETF codes")
        if any(
            product.historical_metrics.history_end != self.as_of
            for product in self.products
        ):
            raise ValueError("KRX product history_end must match report as_of")
        return self


class KrxMarketEvidenceRepository:
    def __init__(self, report: KrxMarketEvidenceReport) -> None:
        self.report = report
        self._products = {product.isu_code: product for product in report.products}
        self.universe = [
            product.historical_metrics for product in report.products
        ]

    @classmethod
    def from_path(cls, path: Path) -> "KrxMarketEvidenceRepository":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(KrxMarketEvidenceReport.model_validate(payload))

    @classmethod
    def from_latest_cache(
        cls,
        cache_root: Path = Path("data/cache/krx"),
    ) -> "KrxMarketEvidenceRepository":
        candidates = sorted(cache_root.glob("etf_market_evidence_*.json"))
        if not candidates:
            raise FileNotFoundError(f"no KRX market evidence report in {cache_root}")
        return cls.from_path(candidates[-1])

    def get(self, isu_code: str) -> KrxEtfEvidenceProduct:
        try:
            return self._products[isu_code]
        except KeyError as exc:
            raise KeyError(
                f"ETF {isu_code} is not current and observation-sufficient"
            ) from exc
