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
    Migration(
        3,
        "chapter_commit_authority",
        """
        ALTER TABLE projects ADD COLUMN authority_mode TEXT NOT NULL DEFAULT 'legacy'
          CHECK (authority_mode IN ('legacy', 'runtime'));
        ALTER TABLE projects ADD COLUMN runtime_finalized_at TEXT;

        ALTER TABLE idempotency_ledger ADD COLUMN request_hash TEXT;
        ALTER TABLE idempotency_ledger ADD COLUMN status_code INTEGER NOT NULL DEFAULT 200;

        ALTER TABLE story_events ADD COLUMN commit_id TEXT;
        ALTER TABLE story_events ADD COLUMN ordinal INTEGER;
        ALTER TABLE story_events ADD COLUMN aggregate_type TEXT;
        ALTER TABLE story_events ADD COLUMN aggregate_id TEXT;
        ALTER TABLE story_events ADD COLUMN schema_version TEXT;
        ALTER TABLE story_events ADD COLUMN created_at TEXT;
        ALTER TABLE story_events ADD COLUMN applied_revision INTEGER;
        CREATE UNIQUE INDEX story_events_commit_ordinal_idx
          ON story_events(project_id, commit_id, ordinal) WHERE commit_id IS NOT NULL;

        ALTER TABLE projection_checkpoints ADD COLUMN applied_revision INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE projection_checkpoints ADD COLUMN event_offset INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE projection_checkpoints ADD COLUMN state_hash TEXT;

        CREATE TABLE chapter_commits (
          commit_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          chapter_number INTEGER NOT NULL CHECK (chapter_number >= 1),
          request_id TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          request_hash TEXT NOT NULL,
          expected_revision INTEGER NOT NULL CHECK (expected_revision >= 0),
          resulting_revision INTEGER CHECK (resulting_revision IS NULL OR resulting_revision >= expected_revision),
          state TEXT NOT NULL CHECK (state IN (
            'PREPARED','VALIDATED','PERSISTING','COMMITTED','PROJECTING','FINALIZED',
            'REJECTED','ABORTED','RECOVERY_REQUIRED'
          )),
          body_sha256 TEXT,
          artifact_sha256 TEXT,
          validation_token TEXT,
          schema_version TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          finalized_at TEXT,
          error_code TEXT,
          error_details_json TEXT NOT NULL DEFAULT '{}',
          UNIQUE(project_id, idempotency_key)
        );
        CREATE UNIQUE INDEX chapter_commits_finalized_chapter_idx
          ON chapter_commits(project_id, chapter_number) WHERE state = 'FINALIZED';
        CREATE INDEX chapter_commits_state_idx ON chapter_commits(project_id, state, updated_at);

        CREATE TABLE chapter_artifacts (
          commit_id TEXT PRIMARY KEY REFERENCES chapter_commits(commit_id) ON DELETE CASCADE,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          chapter_number INTEGER NOT NULL,
          title TEXT NOT NULL,
          body_text TEXT NOT NULL,
          summary TEXT NOT NULL,
          outline_fulfillment_json TEXT NOT NULL,
          review_json TEXT NOT NULL DEFAULT '{}',
          state_mutation_proposal_json TEXT NOT NULL DEFAULT '{}',
          evidence_spans_json TEXT NOT NULL DEFAULT '[]',
          events_json TEXT NOT NULL DEFAULT '[]',
          schema_version TEXT NOT NULL,
          body_sha256 TEXT NOT NULL,
          checksum TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE commit_transitions (
          transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
          commit_id TEXT NOT NULL REFERENCES chapter_commits(commit_id) ON DELETE CASCADE,
          from_state TEXT,
          to_state TEXT NOT NULL,
          reason TEXT NOT NULL,
          request_id TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          project_id TEXT NOT NULL,
          chapter_number INTEGER NOT NULL,
          expected_revision INTEGER NOT NULL,
          resulting_revision INTEGER,
          schema_version TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX commit_transitions_commit_idx ON commit_transitions(commit_id, transition_id);

        CREATE TABLE outbox (
          outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          commit_id TEXT,
          topic TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
          retry_count INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX outbox_pending_idx ON outbox(status, outbox_id);

        CREATE TABLE replay_jobs (
          replay_job_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          request_id TEXT NOT NULL,
          projection_names_json TEXT NOT NULL,
          from_event_sequence INTEGER NOT NULL,
          to_event_sequence INTEGER,
          target_revision INTEGER,
          verify_only INTEGER NOT NULL,
          expected_hash TEXT,
          resulting_hash TEXT,
          state TEXT NOT NULL,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          completed_at TEXT
        );
        """,
        """
        DROP TABLE replay_jobs;
        DROP INDEX outbox_pending_idx;
        DROP TABLE outbox;
        DROP INDEX commit_transitions_commit_idx;
        DROP TABLE commit_transitions;
        DROP TABLE chapter_artifacts;
        DROP INDEX chapter_commits_state_idx;
        DROP INDEX chapter_commits_finalized_chapter_idx;
        DROP TABLE chapter_commits;

        DROP INDEX story_events_commit_ordinal_idx;
        ALTER TABLE projection_checkpoints DROP COLUMN state_hash;
        ALTER TABLE projection_checkpoints DROP COLUMN event_offset;
        ALTER TABLE projection_checkpoints DROP COLUMN applied_revision;
        ALTER TABLE story_events DROP COLUMN applied_revision;
        ALTER TABLE story_events DROP COLUMN created_at;
        ALTER TABLE story_events DROP COLUMN schema_version;
        ALTER TABLE story_events DROP COLUMN aggregate_id;
        ALTER TABLE story_events DROP COLUMN aggregate_type;
        ALTER TABLE story_events DROP COLUMN ordinal;
        ALTER TABLE story_events DROP COLUMN commit_id;
        ALTER TABLE idempotency_ledger DROP COLUMN status_code;
        ALTER TABLE idempotency_ledger DROP COLUMN request_hash;
        ALTER TABLE projects DROP COLUMN runtime_finalized_at;
        ALTER TABLE projects DROP COLUMN authority_mode;
        """,
    ),
    Migration(
        4,
        "unified_review_artifacts",
        """
        CREATE TABLE review_artifacts (
          artifact_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          chapter_number INTEGER NOT NULL, source_revision INTEGER NOT NULL, body_sha256 TEXT NOT NULL,
          reviewer_kind TEXT NOT NULL, artifact_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(project_id, chapter_number, artifact_id)
        );
        CREATE INDEX review_artifacts_chapter_idx ON review_artifacts(project_id, chapter_number, source_revision);
        CREATE TABLE review_findings (
          project_id TEXT NOT NULL, chapter_number INTEGER NOT NULL, artifact_id TEXT NOT NULL REFERENCES review_artifacts(artifact_id) ON DELETE CASCADE,
          finding_id TEXT NOT NULL, fingerprint TEXT NOT NULL, severity TEXT NOT NULL, blocking INTEGER NOT NULL,
          status TEXT NOT NULL, finding_json TEXT NOT NULL, PRIMARY KEY(artifact_id, finding_id)
        );
        CREATE INDEX review_findings_gate_idx ON review_findings(project_id, chapter_number, blocking, status);
        CREATE TABLE human_review_decisions (
          decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          chapter_number INTEGER NOT NULL, source_revision INTEGER NOT NULL, decision TEXT NOT NULL,
          decision_json TEXT NOT NULL, payload_hash TEXT NOT NULL, idempotency_key TEXT NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(project_id, idempotency_key)
        );
        CREATE INDEX human_review_decisions_chapter_idx ON human_review_decisions(project_id, chapter_number, source_revision);
        CREATE TABLE review_finding_decisions (
          decision_id TEXT NOT NULL REFERENCES human_review_decisions(decision_id) ON DELETE CASCADE,
          project_id TEXT NOT NULL, chapter_number INTEGER NOT NULL, source_revision INTEGER NOT NULL,
          fingerprint TEXT NOT NULL, decision TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(decision_id, fingerprint)
        );
        CREATE INDEX review_finding_decisions_effective_idx
          ON review_finding_decisions(project_id, chapter_number, source_revision, fingerprint, created_at);
        CREATE TABLE revision_results (
          result_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          chapter_number INTEGER NOT NULL, source_revision INTEGER NOT NULL, original_body_sha256 TEXT NOT NULL,
          revised_body_sha256 TEXT NOT NULL, requires_reaudit INTEGER NOT NULL, result_json TEXT NOT NULL,
          payload_hash TEXT NOT NULL, original_body_text TEXT NOT NULL, revised_body_text TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE review_operations (
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          idempotency_key TEXT NOT NULL, operation TEXT NOT NULL, request_hash TEXT NOT NULL,
          result_json TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(project_id, operation, idempotency_key)
        );
        """,
        """
        DROP TABLE review_operations;
        DROP TABLE revision_results;
        DROP INDEX review_finding_decisions_effective_idx;
        DROP TABLE review_finding_decisions;
        DROP INDEX human_review_decisions_chapter_idx;
        DROP TABLE human_review_decisions;
        DROP INDEX review_findings_gate_idx;
        DROP TABLE review_findings;
        DROP INDEX review_artifacts_chapter_idx;
        DROP TABLE review_artifacts;
        """,
    ),
    Migration(
        5,
        "studio_observability",
        """
        CREATE TABLE recovery_jobs (
          job_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          operation TEXT NOT NULL,
          state TEXT NOT NULL CHECK (state IN ('previewed','running','completed','failed','cancelled','blocked')),
          requires_confirmation INTEGER NOT NULL,
          confirmation_hash TEXT,
          parameters_json TEXT NOT NULL DEFAULT '{}',
          preview_json TEXT NOT NULL DEFAULT '{}',
          result_json TEXT,
          progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
          cancellable INTEGER NOT NULL DEFAULT 0,
          error_code TEXT,
          error_message TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          completed_at TEXT
        );
        CREATE INDEX recovery_jobs_project_idx ON recovery_jobs(project_id, created_at DESC, job_id DESC);
        CREATE TABLE recovery_audit (
          audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL REFERENCES recovery_jobs(job_id) ON DELETE CASCADE,
          project_id TEXT NOT NULL,
          action TEXT NOT NULL,
          outcome TEXT NOT NULL,
          actor TEXT NOT NULL,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );
        CREATE INDEX recovery_audit_job_idx ON recovery_audit(job_id, audit_id);
        """,
        """
        DROP INDEX recovery_audit_job_idx;
        DROP TABLE recovery_audit;
        DROP INDEX recovery_jobs_project_idx;
        DROP TABLE recovery_jobs;
        """,
    ),
    Migration(
        6,
        "legacy_project_import",
        """
        CREATE TABLE migration_jobs (
          job_id TEXT PRIMARY KEY,
          source_type TEXT NOT NULL CHECK (source_type IN ('inkos','webnovel-writer','hybrid','unknown')),
          source_path TEXT NOT NULL,
          source_path_fingerprint TEXT NOT NULL,
          source_checksum_manifest_json TEXT NOT NULL DEFAULT '[]',
          target_project_id TEXT NOT NULL,
          target_snapshot_json TEXT,
          mapping_version TEXT NOT NULL,
          cir_version TEXT NOT NULL,
          current_stage TEXT NOT NULL CHECK (current_stage IN (
            'DISCOVERED','SCANNED','MAPPED','VALIDATED','AWAITING_DECISIONS','READY',
            'IMPORTING','VERIFYING','COMPLETED','PAUSED','FAILED','ROLLED_BACK','QUARANTINED'
          )),
          resume_stage TEXT,
          progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
          warnings_json TEXT NOT NULL DEFAULT '[]',
          conflicts_json TEXT NOT NULL DEFAULT '[]',
          decisions_json TEXT NOT NULL DEFAULT '{}',
          checkpoints_json TEXT NOT NULL DEFAULT '[]',
          audit_log_json TEXT NOT NULL DEFAULT '[]',
          discovery_json TEXT NOT NULL DEFAULT '{}',
          cir_json TEXT,
          dry_run_json TEXT,
          verification_json TEXT,
          cutover_confirmed INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          completed_at TEXT,
          UNIQUE(source_path_fingerprint, mapping_version, target_project_id)
        );
        CREATE INDEX migration_jobs_target_idx ON migration_jobs(target_project_id, created_at DESC);
        CREATE TABLE migration_import_ledger (
          job_id TEXT NOT NULL REFERENCES migration_jobs(job_id) ON DELETE CASCADE,
          cir_item_id TEXT NOT NULL,
          item_kind TEXT NOT NULL,
          target_key TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL,
          imported_at TEXT NOT NULL,
          PRIMARY KEY(job_id, cir_item_id)
        );
        CREATE INDEX migration_import_ledger_target_idx ON migration_import_ledger(job_id, item_kind);
        CREATE TABLE migration_source_provenance (
          job_id TEXT NOT NULL REFERENCES migration_jobs(job_id) ON DELETE CASCADE,
          cir_item_id TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_sha256 TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          locator_json TEXT NOT NULL DEFAULT '{}',
          confidence REAL NOT NULL DEFAULT 1.0,
          PRIMARY KEY(job_id, cir_item_id, source_path, source_sha256)
        );
        """,
        """
        DROP TABLE migration_source_provenance;
        DROP INDEX migration_import_ledger_target_idx;
        DROP TABLE migration_import_ledger;
        DROP INDEX migration_jobs_target_idx;
        DROP TABLE migration_jobs;
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
