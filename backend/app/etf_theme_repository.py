import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from .engine.etf_theme import EtfThemeCatalog, EtfThemeDefinition, resolve_theme

DEFAULT_THEME_CATALOG_PATH = Path("data/reference/etf_theme_catalog.json")
DEFAULT_KIS_CACHE_ROOT = Path("data/cache/kis")


class EtfThemeRepository:
    """Read stable theme definitions and the latest full KIS ETF snapshot."""

    def __init__(
        self,
        *,
        catalog: EtfThemeCatalog,
        kis_products_by_code: dict[str, dict[str, Any]] | None = None,
        component_snapshot_date: date | None = None,
        catalog_path: Path = DEFAULT_THEME_CATALOG_PATH,
        kis_snapshot_path: Path | None = None,
    ) -> None:
        self.catalog = catalog
        self.kis_products_by_code = kis_products_by_code or {}
        self.component_snapshot_date = component_snapshot_date
        self.catalog_path = catalog_path
        self.kis_snapshot_path = kis_snapshot_path

    @classmethod
    def from_local_cache(
        cls,
        *,
        catalog_path: Path = DEFAULT_THEME_CATALOG_PATH,
        kis_cache_root: Path = DEFAULT_KIS_CACHE_ROOT,
    ) -> "EtfThemeRepository":
        catalog = EtfThemeCatalog.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
        snapshot_paths = sorted(kis_cache_root.glob("etf_snapshot_*.json"))
        if not snapshot_paths:
            return cls(catalog=catalog, catalog_path=catalog_path)

        snapshot_path = snapshot_paths[-1]
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        products = payload.get("products")
        if not isinstance(products, list):
            raise ValueError("KIS ETF snapshot must contain a products array")
        by_code = {
            str(product["isu_code"]): product
            for product in products
            if isinstance(product, dict) and product.get("isu_code")
        }
        snapshot_date = date.fromisoformat(str(payload["snapshot_date"]))
        return cls(
            catalog=catalog,
            kis_products_by_code=by_code,
            component_snapshot_date=snapshot_date,
            catalog_path=catalog_path,
            kis_snapshot_path=snapshot_path,
        )

    def list(self) -> tuple[EtfThemeDefinition, ...]:
        return self.catalog.themes

    def get(self, theme_id: str) -> EtfThemeDefinition | None:
        return next(
            (theme for theme in self.catalog.themes if theme.theme_id == theme_id),
            None,
        )

    def resolve(self, message: str) -> EtfThemeDefinition | None:
        return resolve_theme(self.catalog, message)


@lru_cache(maxsize=1)
def get_default_etf_theme_repository() -> EtfThemeRepository:
    return EtfThemeRepository.from_local_cache()
