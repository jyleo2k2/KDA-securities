import json
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_ETF_PRODUCT_DESCRIPTION_PATH = Path(
    "data/reference/etf_product_descriptions.json"
)


class EtfProductDescription(BaseModel):
    """Approved descriptive content joined to market data by ETF product name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product_name: str = Field(min_length=1)
    full_description: str = Field(min_length=1)
    one_line_description: str = Field(min_length=1)
    source_document_ids: tuple[str, ...] = Field(min_length=1)
    as_of_date: date


class _EtfProductDescriptionCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^\d+\.\d+$")
    catalog_version: str = Field(min_length=1)
    products: tuple[EtfProductDescription, ...]


def _normalized_product_name(product_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", product_name).casefold()
    return "".join(normalized.split())


class EtfProductDescriptionRepository:
    """Exact normalized-name lookup for approved ETF product descriptions."""

    def __init__(
        self,
        descriptions: tuple[EtfProductDescription, ...],
        *,
        catalog_version: str = "unversioned",
        source_path: Path | None = None,
    ) -> None:
        by_name: dict[str, EtfProductDescription] = {}
        for description in descriptions:
            normalized_name = _normalized_product_name(description.product_name)
            if not normalized_name:
                raise ValueError("ETF product name must not be blank")
            existing = by_name.get(normalized_name)
            if existing is not None:
                raise ValueError(
                    "ETF product description normalized-name collision: "
                    f"{existing.product_name!r} and {description.product_name!r}"
                )
            by_name[normalized_name] = description

        self.catalog_version = catalog_version
        self.source_path = source_path
        self._by_name = by_name

    @classmethod
    def from_local_path(
        cls,
        path: Path = DEFAULT_ETF_PRODUCT_DESCRIPTION_PATH,
    ) -> "EtfProductDescriptionRepository":
        payload = json.loads(path.read_text(encoding="utf-8"))
        catalog = _EtfProductDescriptionCatalog.model_validate(payload)
        return cls(
            catalog.products,
            catalog_version=catalog.catalog_version,
            source_path=path,
        )

    def get(self, product_name: str) -> EtfProductDescription | None:
        normalized_name = _normalized_product_name(product_name)
        if not normalized_name:
            return None
        return self._by_name.get(normalized_name)

    def __len__(self) -> int:
        return len(self._by_name)


@lru_cache(maxsize=1)
def get_default_etf_product_description_repository() -> EtfProductDescriptionRepository:
    return EtfProductDescriptionRepository.from_local_path()
