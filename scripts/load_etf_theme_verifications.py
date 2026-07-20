"""Load the approved 23 themes x 5 content topics into Supabase."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.etf_theme_repository import EtfThemeRepository
from backend.app.ingestion.etf_theme_verification import (
    DEFAULT_EVIDENCE_MANIFEST,
    ETF_THEME_CONTENT_TOPICS,
    ThemeEvidenceManifestError,
    load_theme_evidence_manifest,
    load_theme_verification_ledger,
)
from backend.app.settings import get_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="승인된 ETF 테마 검증 장부를 적재합니다."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_EVIDENCE_MANIFEST)
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository = EtfThemeRepository.from_local_cache()
    try:
        manifest = load_theme_evidence_manifest(repository, args.manifest.resolve())
    except ThemeEvidenceManifestError as error:
        print(f"ETF 테마 근거 검증 실패: {error}", file=sys.stderr)
        return 1
    expected_count = len(manifest.themes) * len(ETF_THEME_CONTENT_TOPICS)
    print(
        f"ETF 테마 근거 검증 완료: {len(manifest.themes)}개 테마, "
        f"{expected_count}개 질문 유형"
    )
    if args.validate_only:
        return 0

    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        print("DATABASE_URL이 비어 있습니다 (.env 확인)", file=sys.stderr)
        return 1
    try:
        result = load_theme_verification_ledger(
            database_url,
            repository=repository,
            manifest=manifest,
        )
    except (RuntimeError, ValueError, OSError) as error:
        print(f"ETF 테마 검증 장부 적재 실패: {error}", file=sys.stderr)
        return 1
    print(
        f"ETF 테마 검증 장부 적재 완료: 검토 {result.review_count}건, "
        f"근거 {result.evidence_count}건"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
