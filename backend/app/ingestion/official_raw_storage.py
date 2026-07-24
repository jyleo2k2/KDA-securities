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
OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET = "official-etf-universe-reference-raw"
RAW_RETENTION_DAYS = 365
MAX_DELETE_PATHS_PER_REQUEST = 1000


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
    directories: dict[str, Path] | None = None,
) -> RawRunManifest:
    if not run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("run_id must be a single path segment")
    artifact_paths = _artifact_paths(files=files, directories=directories or {})
    artifacts = [
        _raw_artifact(run_id=run_id, source=source, relative_path=relative, path=path)
        for source, relative, path in artifact_paths
    ]

    collected = collected_at.astimezone(UTC)
    return RawRunManifest(
        run_id=run_id,
        collected_at=collected.isoformat(),
        retention_until=(
            collected.date() + timedelta(days=RAW_RETENTION_DAYS)
        ).isoformat(),
        artifacts=tuple(artifacts),
    )


def _artifact_paths(
    *, files: dict[str, Path], directories: dict[str, Path]
) -> list[tuple[str, Path, Path]]:
    entries: list[tuple[str, Path, Path]] = []
    for source, path in files.items():
        _validate_source(source)
        entries.append((source, Path(path.name), path))
    for source, directory in directories.items():
        _validate_source(source)
        if not directory.is_dir():
            raise ValueError(f"official raw directory does not exist: {directory}")
        entries.extend(
            (source, path.relative_to(directory), path)
            for path in directory.rglob("*")
            if path.is_file()
        )
    if not entries:
        raise ValueError("official raw manifest requires at least one file")
    return sorted(entries, key=lambda item: (item[0], item[1].as_posix()))


def _validate_source(source: str) -> None:
    if not source or "/" in source or "\\" in source:
        raise ValueError("source must be a single path segment")


def _raw_artifact(
    *, run_id: str, source: str, relative_path: Path, path: Path
) -> RawArtifact:
    content = path.read_bytes()
    normalized_relative = relative_path.as_posix()
    artifact_source = (
        source
        if normalized_relative == path.name
        else f"{source}/{normalized_relative}"
    )
    return RawArtifact(
        source=artifact_source,
        object_path=f"runs/{run_id}/{source}/{normalized_relative}",
        sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
    )


class OfficialRawStorage:
    """Writes server-only artifacts; no browser credential or signed URL is exposed."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_key: str,
        bucket_name: str = OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET,
        client: httpx.Client | None = None,
    ) -> None:
        if not supabase_url.strip() or not service_key.strip():
            raise ValueError("Supabase URL and server secret are required")
        _validate_source(bucket_name)
        self._base_url = supabase_url.rstrip("/")
        self._service_key = service_key
        self._bucket_name = bucket_name
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0))

    def upload_run(
        self,
        *,
        files: dict[str, Path],
        run_id: str,
        collected_at: datetime | None = None,
        directories: dict[str, Path] | None = None,
    ) -> RawRunManifest:
        manifest = build_raw_run_manifest(
            run_id=run_id,
            files=files,
            collected_at=collected_at or datetime.now(UTC),
            directories=directories,
        )
        for artifact in manifest.artifacts:
            source_path = _source_path_for_artifact(
                artifact=artifact,
                files=files,
                directories=directories or {},
            )
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

    def promote_current_run(self, *, dataset: str, manifest: RawRunManifest) -> None:
        """Point a server-only dataset alias at one complete immutable run."""

        _validate_source(dataset)
        self._upload(
            f"current/{dataset}.json",
            json.dumps(
                {
                    "manifest_path": f"runs/{manifest.run_id}/manifest.json",
                    "run_id": manifest.run_id,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            content_type="application/json",
        )

    def delete_paths(self, paths: list[str]) -> int:
        """Permanently remove server-owned raw paths through the Storage API."""

        normalized = sorted(set(paths))
        if not normalized:
            return 0
        if any(
            not path.startswith("runs/") or path.endswith("/")
            for path in normalized
        ):
            raise ValueError("only concrete raw run object paths may be deleted")
        for batch_start in range(0, len(normalized), MAX_DELETE_PATHS_PER_REQUEST):
            batch = normalized[
                batch_start : batch_start + MAX_DELETE_PATHS_PER_REQUEST
            ]
            response = self._client.request(
                "DELETE",
                f"{self._base_url}/storage/v1/object/"
                f"{self._bucket_name}",
                json={"prefixes": batch},
                headers={
                    "apikey": self._service_key,
                    "authorization": f"Bearer {self._service_key}",
                },
            )
            if response.is_error:
                raise OfficialRawStorageError(
                    f"official raw deletion failed with HTTP {response.status_code}"
                )
        return len(normalized)

    def _upload(self, object_path: str, content: bytes, *, content_type: str) -> None:
        response = self._client.put(
            f"{self._base_url}/storage/v1/object/"
            f"{self._bucket_name}/{quote(object_path, safe='/')}",
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


def _source_path_for_artifact(
    *,
    artifact: RawArtifact,
    files: dict[str, Path],
    directories: dict[str, Path],
) -> Path:
    _, _, source, relative_path = artifact.object_path.split("/", 3)
    if source in files and relative_path == files[source].name:
        return files[source]
    directory = directories.get(source)
    if directory is None:
        raise ValueError(f"no local source for raw artifact: {artifact.object_path}")
    return directory / Path(relative_path)
