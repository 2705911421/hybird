from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from .config import RuntimeConfig
from .migrations import MIGRATIONS, MigrationEngine


class Database:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.path = Path(config.database_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.path,
            timeout=self.config.busy_timeout_ms / 1000,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={self.config.busy_timeout_ms}")
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
        finally:
            conn.close()

    @property
    def migrations(self) -> MigrationEngine:
        return MigrationEngine(self.connect)

    @property
    def latest_schema_version(self) -> int:
        return MIGRATIONS[-1].version
