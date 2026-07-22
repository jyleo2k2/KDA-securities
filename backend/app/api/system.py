from fastapi import APIRouter
from starlette.responses import RedirectResponse

from ..etf_theme_repository import get_default_etf_theme_repository

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@router.get("/health")
def health() -> dict[str, str | int]:
    catalog = get_default_etf_theme_repository().catalog
    return {
        "status": "ok",
        "etf_theme_catalog_version": catalog.catalog_version,
        "etf_theme_count": len(catalog.themes),
    }
