from fastapi import APIRouter
from starlette.responses import RedirectResponse

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
