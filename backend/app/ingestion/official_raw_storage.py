"""Private Supabase Storage boundary for official ETF distribution raw files."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx

OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET = "official-etf-distribution-raw"
RAW_RETENTION_DAYS = 365


class OfficialRawStorageError(RuntimeError):
    """Raised when a private official raw artifact cannot be stored."""


@dataclass(frozen=True, slots=True)
class RawArtifact:
    source: str
    object_path: str
    sha256: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class RawRunManifest:
    run_id: str
    collected_at: str
    retention_until: str
    artifacts: tuple[RawArtifact, ...]

    def as_json(self) -> bytes:
        return json.dumps(
            {
                "artifacts": [asdict(artifact) for artifact in self.artifacts],
                "collected_at": self.collected_at,
                "retention_until": self.retention_until,
                "run_id": self.run_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


def build_raw_run_manifest(
    *,
    run_id: str,
    files: dict[str, Path],
    collected_at: datetime,
) -> RawRunManifest:
    if not run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("run_id must be a single path segment")
    if not files:
        raise ValueError("official raw manifest requires at least one file")

    artifacts = []
    for source, path in sorted(files.items()):
        if not source or "/" in source or "\\" in source:
            raise ValueError("source must be a single path segment")
        content = path.read_bytes()
        artifacts.append(
            RawArtifact(
                source=source,
                object_path=f"runs/{run_id}/{source}/{path.name}",
                sha256=hashlib.sha256(content).hexdigest(),
                byte_count=len(content),
            )
        )

    collected = collected_at.astimezone(UTC)
    return RawRunManifest(
        run_id=run_id,
        collected_at=collected.isoformat(),
        retention_until=(
            collected.date() + timedelta(days=RAW_RETENTION_DAYS)
        ).isoformat(),
        artifacts=tuple(artifacts),
    )


class OfficialRawStorage:
    """Writes server-only artifacts; no browser credential or signed URL is exposed."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not supabase_url.strip() or not service_key.strip():
            raise ValueError("Supabase URL and server secret are required")
        self._base_url = supabase_url.rstrip("/")
        self._service_key = service_key
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0))

    def upload_run(
        self,
        *,
        files: dict[str, Path],
        run_id: str,
        collected_at: datetime | None = None,
    ) -> RawRunManifest:
        manifest = build_raw_run_manifest(
            run_id=run_id,
            files=files,
            collected_at=collected_at or datetime.now(UTC),
        )
        for artifact in manifest.artifacts:
            source_path = files[artifact.source]
            self._upload(
                artifact.object_path,
                source_path.read_bytes(),
                content_type="application/octet-stream",
            )
        self._upload(
            f"runs/{manifest.run_id}/manifest.json",
            manifest.as_json(),
            content_type="application/json",
        )
        return manifest

    def _upload(self, object_path: str, content: bytes, *, content_type: str) -> None:
        response = self._client.put(
            f"{self._base_url}/storage/v1/object/"
            f"{OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET}/{quote(object_path, safe='/')}",
            content=content,
            headers={
                "apikey": self._service_key,
                "authorization": f"Bearer {self._service_key}",
                "content-type": content_type,
                "x-upsert": "true",
            },
        )
        if response.is_error:
            raise OfficialRawStorageError(
                f"official raw upload failed with HTTP {response.status_code}"
            )
