from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    database_path: Path
    local_token: str = "story-runtime-local"
    busy_timeout_ms: int = 750
    writes_enabled: bool = False
    projection_root: Path | None = None
    unified_review_enabled: bool = False
    observability_enabled: bool = True
    recovery_enabled: bool = True
    migration_enabled: bool = True
    migration_max_file_bytes: int = 64 * 1024 * 1024
    migration_max_total_bytes: int = 4 * 1024 * 1024 * 1024
    migration_max_files: int = 200_000
    wal_autocheckpoint_pages: int = 1000
    journal_size_limit_bytes: int = 64 * 1024 * 1024
    log_path: Path | None = None
    log_max_bytes: int = 10 * 1024 * 1024
    log_backups: int = 5
    max_request_bytes: int = 16 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            database_path=Path(os.getenv("STORY_RUNTIME_DB", "./data/story.db")).expanduser().resolve(),
            local_token=os.getenv("STORY_RUNTIME_TOKEN", "story-runtime-local"),
            busy_timeout_ms=int(os.getenv("STORY_RUNTIME_BUSY_TIMEOUT_MS", "750")),
            writes_enabled=os.getenv("STORY_RUNTIME_ENABLE_WRITES", "0") == "1",
            projection_root=Path(os.environ["STORY_RUNTIME_PROJECTION_ROOT"]).expanduser().resolve()
            if os.getenv("STORY_RUNTIME_PROJECTION_ROOT") else None,
            unified_review_enabled=os.getenv("STORY_RUNTIME_UNIFIED_REVIEW_ENABLED", "0") == "1",
            observability_enabled=os.getenv("STORY_RUNTIME_OBSERVABILITY_ENABLED", "1") == "1",
            recovery_enabled=os.getenv("STORY_RUNTIME_RECOVERY_ENABLED", "1") == "1",
            migration_enabled=os.getenv("STORY_RUNTIME_MIGRATION_ENABLED", "1") == "1",
            migration_max_file_bytes=int(os.getenv("STORY_RUNTIME_MIGRATION_MAX_FILE_BYTES", str(64 * 1024 * 1024))),
            migration_max_total_bytes=int(os.getenv("STORY_RUNTIME_MIGRATION_MAX_TOTAL_BYTES", str(4 * 1024 * 1024 * 1024))),
            migration_max_files=int(os.getenv("STORY_RUNTIME_MIGRATION_MAX_FILES", "200000")),
            wal_autocheckpoint_pages=int(os.getenv("STORY_RUNTIME_WAL_AUTOCHECKPOINT_PAGES", "1000")),
            journal_size_limit_bytes=int(os.getenv("STORY_RUNTIME_JOURNAL_SIZE_LIMIT_BYTES", str(64 * 1024 * 1024))),
            log_path=Path(os.environ["STORY_RUNTIME_LOG_PATH"]).expanduser().resolve()
            if os.getenv("STORY_RUNTIME_LOG_PATH") else None,
            log_max_bytes=int(os.getenv("STORY_RUNTIME_LOG_MAX_BYTES", str(10 * 1024 * 1024))),
            log_backups=int(os.getenv("STORY_RUNTIME_LOG_BACKUPS", "5")),
            max_request_bytes=int(os.getenv("STORY_RUNTIME_MAX_REQUEST_BYTES", str(16 * 1024 * 1024))),
        )
