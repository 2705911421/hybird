from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION, __version__
from .chapter_commits import ChapterCommitService
from .config import RuntimeConfig
from .database import Database
from .repository import StoryRepository
from .services import RuntimeServices


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Compatibility:
    status: str
    app_version: str
    runtime_version: str
    api_contract: str
    database_schema: int
    supported_database_schema: int
    project_schemas: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["project_schemas"] = list(self.project_schemas)
        return value


def compatibility(database: Database, *, app_version: str = "1.7.0", runtime_version: str = __version__) -> Compatibility:
    current = database.migrations.current_version()
    latest = database.latest_schema_version
    status = "compatible" if current == latest else "migration_required" if current < latest else "schema_too_new"
    return Compatibility(status, app_version, runtime_version, SCHEMA_VERSION, current, latest, (SCHEMA_VERSION,))


def create_snapshot(database: Database, destination: Path, *, project_id: str | None = None) -> dict[str, Any]:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="story-runtime-snapshot-") as tmp:
        db_copy = Path(tmp) / "authority.db"
        source = sqlite3.connect(database.path, timeout=database.config.busy_timeout_ms / 1000)
        target = sqlite3.connect(db_copy)
        try:
            source.backup(target, pages=256)
        finally:
            target.close()
            source.close()
        check = sqlite3.connect(db_copy)
        try:
            check.row_factory = sqlite3.Row
            integrity = str(check.execute("PRAGMA integrity_check").fetchone()[0])
            schema_version = int(check.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0])
            if project_id:
                row = check.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
                if row is None:
                    raise ValueError(f"unknown project: {project_id}")
                project_revision = int(row[0])
                projection_hash = ChapterCommitService(database).projection_hash(check, project_id)
            else:
                project_revision = None
                projection_hash = None
        finally:
            check.close()
        if integrity != "ok":
            raise RuntimeError(f"snapshot integrity check failed: {integrity}")
        manifest = {
            "format": "hybrid-story-runtime-snapshot/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.7.0",
            "runtime_version": __version__,
            "schema_version": schema_version,
            "project_schema": SCHEMA_VERSION,
            "project_id": project_id,
            "project_revision": project_revision,
            "projection_hash": projection_hash,
            "database": {"path": "authority.db", "sha256": _sha256(db_copy), "bytes": db_copy.stat().st_size},
            "blobs": [],
            "indexes_rebuild_required": True,
        }
        manifest_path = Path(tmp) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(db_copy, "authority.db")
            archive.write(manifest_path, "manifest.json")
    return manifest | {"snapshot_path": str(destination), "snapshot_sha256": _sha256(destination)}


def restore_snapshot(snapshot: Path, target_dir: Path) -> dict[str, Any]:
    snapshot = snapshot.resolve(strict=True)
    target_dir = target_dir.resolve()
    if target_dir.exists() and any(target_dir.iterdir()):
        raise FileExistsError("restore target must be a new or empty directory")
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(snapshot) as archive:
            names = set(archive.namelist())
            if names != {"authority.db", "manifest.json"}:
                raise ValueError("snapshot contains unexpected or missing entries")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "hybrid-story-runtime-snapshot/v1":
                raise ValueError("unsupported snapshot format")
            db_path = target_dir / "authority.db"
            with archive.open("authority.db") as source, db_path.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
        if _sha256(db_path) != manifest["database"]["sha256"]:
            raise ValueError("snapshot database checksum mismatch")
        database = Database(RuntimeConfig(database_path=db_path))
        compat = compatibility(database)
        if compat.status == "schema_too_new":
            raise ValueError("snapshot database schema is newer than this Runtime")
        with database.connect() as conn:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise ValueError(f"restored database integrity check failed: {integrity}")
        project_id = manifest.get("project_id")
        expected_projection_hash = manifest.get("projection_hash")
        projection_hash = None
        doctor = None
        if compat.status == "compatible" and project_id:
            with database.read() as conn:
                projection_hash = ChapterCommitService(database).projection_hash(conn, project_id)
            if expected_projection_hash and projection_hash != expected_projection_hash:
                raise ValueError("restored projection hash does not match snapshot manifest")
            repository = StoryRepository(database)
            doctor = RuntimeServices(database, repository).doctor(project_id, deep=True).model_dump(mode="json")
        return {
            "target_database": str(db_path), "integrity": integrity,
            "compatibility": compat.as_dict(), "projection_hash": projection_hash,
            "doctor": doctor, "manifest": manifest,
        }
    except Exception:
        db_path = target_dir / "authority.db"
        if db_path.exists():
            db_path.unlink()
        if target_dir.exists() and not any(target_dir.iterdir()):
            target_dir.rmdir()
        raise
