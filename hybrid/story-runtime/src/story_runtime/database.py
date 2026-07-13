from __future__ import annotations

import sqlite3
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from .config import RuntimeConfig
from .migrations import MIGRATIONS, MigrationEngine


class Database:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.path = Path(config.database_path)
        self._connection_lock = threading.Lock()
        self._active_connections = 0

    def _configure(self, conn: sqlite3.Connection, *, writable: bool) -> None:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={self.config.busy_timeout_ms}")
        if writable:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(f"PRAGMA wal_autocheckpoint={self.config.wal_autocheckpoint_pages}")
            conn.execute(f"PRAGMA journal_size_limit={self.config.journal_size_limit_bytes}")
        else:
            conn.execute("PRAGMA query_only=ON")

    @contextmanager
    def connect(self, *, writable: bool = True) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        target = self.path if writable else f"file:{self.path.as_posix()}?mode=ro"
        conn = sqlite3.connect(
            target,
            timeout=self.config.busy_timeout_ms / 1000,
            isolation_level=None,
            check_same_thread=False,
            uri=not writable,
        )
        try:
            self._configure(conn, writable=writable)
            with self._connection_lock:
                self._active_connections += 1
            yield conn
        finally:
            with self._connection_lock:
                self._active_connections = max(0, self._active_connections - 1)
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        with self.connect(writable=False) as conn:
            yield conn

    def checkpoint(self, mode: str = "PASSIVE") -> tuple[int, int, int]:
        normalized = mode.upper()
        if normalized not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError(f"unsupported checkpoint mode: {mode}")
        with self.connect() as conn:
            row = conn.execute(f"PRAGMA wal_checkpoint({normalized})").fetchone()
            return int(row[0]), int(row[1]), int(row[2])

    def filesystem_warning(self) -> str | None:
        raw = str(self.path)
        if raw.startswith("\\\\") or raw.startswith("//"):
            return "SQLite authority databases on UNC/NFS/network shares are unsupported; move the project to a local disk."
        if os.getenv("STORY_RUNTIME_ASSUME_NETWORK_FS") == "1":
            return "The database path is marked as a network filesystem; SQLite authority storage is unsupported there."
        return None

    @property
    def active_connections(self) -> int:
        with self._connection_lock:
            return self._active_connections

    @property
    def migrations(self) -> MigrationEngine:
        return MigrationEngine(self.connect)

    @property
    def latest_schema_version(self) -> int:
        return MIGRATIONS[-1].version
