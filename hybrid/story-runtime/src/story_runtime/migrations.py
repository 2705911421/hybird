from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: str
    down: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.up.encode("utf-8")).hexdigest()


MIGRATIONS = (
    Migration(
        1,
        "authority_core",
        """
        CREATE TABLE projects (
          project_id TEXT PRIMARY KEY,
          revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
          phase TEXT NOT NULL DEFAULT 'initialized',
          latest_chapter INTEGER NOT NULL DEFAULT 0 CHECK (latest_chapter >= 0),
          schema_version TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE entities (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          entity_id TEXT NOT NULL,
          entity_type TEXT NOT NULL,
          canonical_name TEXT NOT NULL,
          aliases_json TEXT NOT NULL DEFAULT '[]',
          attributes_json TEXT NOT NULL DEFAULT '{}',
          history_json TEXT NOT NULL DEFAULT '[]',
          PRIMARY KEY (project_id, entity_id)
        );
        CREATE TABLE relationships (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          relationship_id TEXT NOT NULL,
          source_entity_id TEXT NOT NULL,
          target_entity_id TEXT NOT NULL,
          relationship_type TEXT NOT NULL,
          attributes_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (project_id, relationship_id)
        );
        CREATE TABLE story_events (
          sequence INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          event_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          subject TEXT NOT NULL,
          chapter_number INTEGER,
          payload_json TEXT NOT NULL,
          evidence_json TEXT NOT NULL DEFAULT '[]',
          confidence REAL NOT NULL DEFAULT 1.0,
          UNIQUE (project_id, event_id)
        );
        CREATE TABLE timeline (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          timeline_id TEXT NOT NULL,
          sequence_key TEXT NOT NULL,
          title TEXT NOT NULL,
          event_id TEXT,
          details_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (project_id, timeline_id)
        );
        CREATE TABLE narrative_threads (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          thread_id TEXT NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          introduced_chapter INTEGER NOT NULL,
          resolved_chapter INTEGER,
          details_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (project_id, thread_id)
        );
        CREATE TABLE chapter_summaries (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          chapter_number INTEGER NOT NULL,
          title TEXT NOT NULL,
          summary TEXT NOT NULL,
          body_sha256 TEXT,
          PRIMARY KEY (project_id, chapter_number)
        );
        CREATE TABLE facts (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          fact_id TEXT NOT NULL,
          subject TEXT NOT NULL,
          predicate TEXT NOT NULL,
          value_json TEXT NOT NULL,
          valid_from_revision INTEGER NOT NULL DEFAULT 0,
          valid_to_revision INTEGER,
          PRIMARY KEY (project_id, fact_id)
        );
        CREATE INDEX facts_subject_idx ON facts(project_id, subject, predicate);
        CREATE TABLE idempotency_ledger (
          project_id TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          operation TEXT NOT NULL,
          result_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (project_id, idempotency_key)
        );
        CREATE TABLE projection_checkpoints (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          projection_name TEXT NOT NULL,
          status TEXT NOT NULL,
          checkpoint INTEGER NOT NULL DEFAULT 0,
          retry_count INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (project_id, projection_name)
        );
        CREATE TABLE runtime_incidents (
          incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          component TEXT NOT NULL,
          state TEXT NOT NULL,
          message TEXT NOT NULL,
          retryable INTEGER NOT NULL,
          repair_action TEXT,
          created_at TEXT NOT NULL,
          resolved_at TEXT
        );
        """,
        """
        DROP TABLE runtime_incidents;
        DROP TABLE projection_checkpoints;
        DROP TABLE idempotency_ledger;
        DROP TABLE facts;
        DROP TABLE chapter_summaries;
        DROP TABLE narrative_threads;
        DROP TABLE timeline;
        DROP TABLE story_events;
        DROP TABLE relationships;
        DROP TABLE entities;
        DROP TABLE projects;
        """,
    ),
    Migration(
        2,
        "deterministic_retrieval",
        """
        CREATE TABLE retrieval_documents (
          row_id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          source_id TEXT NOT NULL,
          source_type TEXT NOT NULL,
          chapter_number INTEGER,
          text TEXT NOT NULL,
          UNIQUE (project_id, source_id)
        );
        CREATE VIRTUAL TABLE retrieval_fts USING fts5(
          project_id UNINDEXED, source_id UNINDEXED, text, tokenize='unicode61'
        );
        CREATE TRIGGER retrieval_ai AFTER INSERT ON retrieval_documents BEGIN
          INSERT INTO retrieval_fts(rowid, project_id, source_id, text)
          VALUES (new.row_id, new.project_id, new.source_id, new.text);
        END;
        CREATE TRIGGER retrieval_ad AFTER DELETE ON retrieval_documents BEGIN
          DELETE FROM retrieval_fts WHERE rowid = old.row_id;
        END;
        CREATE TRIGGER retrieval_au AFTER UPDATE ON retrieval_documents BEGIN
          DELETE FROM retrieval_fts WHERE rowid = old.row_id;
          INSERT INTO retrieval_fts(rowid, project_id, source_id, text)
          VALUES (new.row_id, new.project_id, new.source_id, new.text);
        END;
        """,
        """
        DROP TRIGGER retrieval_au;
        DROP TRIGGER retrieval_ad;
        DROP TRIGGER retrieval_ai;
        DROP TABLE retrieval_fts;
        DROP TABLE retrieval_documents;
        """,
    ),
)


class MigrationEngine:
    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    def _ensure_ledger(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL)"""
        )

    def current_version(self) -> int:
        with self.connection_factory() as conn:
            self._ensure_ledger(conn)
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
            return int(row[0])

    def migrate(self, target: int | None = None) -> int:
        target = target if target is not None else MIGRATIONS[-1].version
        if target < 0 or target > MIGRATIONS[-1].version:
            raise ValueError(f"unsupported migration target: {target}")
        with self.connection_factory() as conn:
            self._ensure_ledger(conn)
            applied = {int(r[0]): r[1] for r in conn.execute("SELECT version, checksum FROM schema_migrations")}
            for migration in MIGRATIONS:
                if migration.version in applied and applied[migration.version] != migration.checksum:
                    raise RuntimeError(f"migration checksum drift: {migration.version}")
            current = max(applied, default=0)
            if current < target:
                for migration in MIGRATIONS:
                    if current < migration.version <= target:
                        applied_at = datetime.now(timezone.utc).isoformat()
                        values = (migration.name, migration.checksum, applied_at)
                        escaped = tuple(value.replace("'", "''") for value in values)
                        conn.executescript(
                            "BEGIN IMMEDIATE;\n"
                            + migration.up
                            + f"\nINSERT INTO schema_migrations VALUES ({migration.version}, '{escaped[0]}', '{escaped[1]}', '{escaped[2]}');\nCOMMIT;"
                        )
            elif current > target:
                for migration in reversed(MIGRATIONS):
                    if target < migration.version <= current:
                        conn.executescript(
                            "BEGIN IMMEDIATE;\n"
                            + migration.down
                            + f"\nDELETE FROM schema_migrations WHERE version = {migration.version};\nCOMMIT;"
                        )
        return target
