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
    original_filename: str | None = None


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
    storage_relative = _storage_relative_path(relative_path, path=path)
    artifact_source = (
        source
        if normalized_relative == path.name
        else f"{source}/{normalized_relative}"
    )
    return RawArtifact(
        source=artifact_source,
        object_path=f"runs/{run_id}/{source}/{storage_relative.as_posix()}",
        sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
        original_filename=path.name,
    )


def _storage_relative_path(relative_path: Path, *, path: Path) -> Path:
    """Use an ASCII object key for a direct source file without losing its name."""

    if relative_path.as_posix() != path.name or path.name.isascii():
        return relative_path
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]
    return Path(f"source-{digest}{path.suffix.lower()}")


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

    def materialize_current_run(
        self, *, dataset: str, destination: Path
    ) -> RawRunManifest:
        """Download one promoted immutable run after validating every artifact hash."""

        _validate_source(dataset)
        pointer = self._load_json(f"current/{dataset}.json")
        manifest_path = pointer.get("manifest_path")
        run_id = pointer.get("run_id")
        if (
            not isinstance(manifest_path, str)
            or not isinstance(run_id, str)
            or manifest_path != f"runs/{run_id}/manifest.json"
        ):
            raise OfficialRawStorageError("official raw current pointer is invalid")
        manifest = _manifest_from_json(self._load_json(manifest_path))
        if manifest.run_id != run_id:
            raise OfficialRawStorageError("official raw current pointer run is invalid")
        for artifact in manifest.artifacts:
            relative_path = _destination_path(
                artifact=artifact,
                run_id=manifest.run_id,
            )
            content = self._download(artifact.object_path)
            if len(content) != artifact.byte_count:
                raise OfficialRawStorageError(
                    f"official raw artifact byte count mismatch: {artifact.source}"
                )
            if hashlib.sha256(content).hexdigest() != artifact.sha256:
                raise OfficialRawStorageError(
                    f"official raw artifact hash mismatch: {artifact.source}"
                )
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
        return manifest

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

    def _download(self, object_path: str) -> bytes:
        response = self._client.get(
            f"{self._base_url}/storage/v1/object/"
            f"{self._bucket_name}/{quote(object_path, safe='/')}",
            headers={
                "apikey": self._service_key,
                "authorization": f"Bearer {self._service_key}",
            },
        )
        if response.is_error:
            raise OfficialRawStorageError(
                f"official raw download failed with HTTP {response.status_code}"
            )
        return response.content

    def _load_json(self, object_path: str) -> dict[str, object]:
        try:
            payload = json.loads(self._download(object_path))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OfficialRawStorageError(
                f"official raw JSON is invalid: {object_path}"
            ) from error
        if not isinstance(payload, dict):
            raise OfficialRawStorageError(
                f"official raw JSON is invalid: {object_path}"
            )
        return payload


def _source_path_for_artifact(
    *,
    artifact: RawArtifact,
    files: dict[str, Path],
    directories: dict[str, Path],
) -> Path:
    _, _, source, relative_path = artifact.object_path.split("/", 3)
    if source in files:
        return files[source]
    directory = directories.get(source)
    if directory is None:
        raise ValueError(f"no local source for raw artifact: {artifact.object_path}")
    return directory / Path(relative_path)


def _manifest_from_json(payload: dict[str, object]) -> RawRunManifest:
    run_id = payload.get("run_id")
    collected_at = payload.get("collected_at")
    retention_until = payload.get("retention_until")
    raw_artifacts = payload.get("artifacts")
    if (
        not isinstance(run_id, str)
        or not isinstance(collected_at, str)
        or not isinstance(retention_until, str)
        or not isinstance(raw_artifacts, list)
    ):
        raise OfficialRawStorageError("official raw manifest is invalid")
    artifacts = []
    for raw_artifact in raw_artifacts:
        if not isinstance(raw_artifact, dict):
            raise OfficialRawStorageError("official raw manifest artifact is invalid")
        source = raw_artifact.get("source")
        object_path = raw_artifact.get("object_path")
        sha256 = raw_artifact.get("sha256")
        byte_count = raw_artifact.get("byte_count")
        original_filename = raw_artifact.get("original_filename")
        if (
            not isinstance(source, str)
            or not isinstance(object_path, str)
            or not isinstance(sha256, str)
            or not isinstance(byte_count, int)
            or len(sha256) != 64
            or (
                original_filename is not None
                and not isinstance(original_filename, str)
            )
        ):
            raise OfficialRawStorageError("official raw manifest artifact is invalid")
        artifacts.append(
            RawArtifact(
                source=source,
                object_path=object_path,
                sha256=sha256,
                byte_count=byte_count,
                original_filename=original_filename,
            )
        )
    return RawRunManifest(
        run_id=run_id,
        collected_at=collected_at,
        retention_until=retention_until,
        artifacts=tuple(artifacts),
    )


def _destination_path(*, artifact: RawArtifact, run_id: str) -> Path:
    prefix = f"runs/{run_id}/"
    if not artifact.object_path.startswith(prefix):
        raise OfficialRawStorageError("official raw artifact path is invalid")
    relative = Path(artifact.object_path.removeprefix(prefix))
    if relative.is_absolute() or ".." in relative.parts:
        raise OfficialRawStorageError("official raw artifact path is unsafe")
    return relative
