from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import SCHEMA_VERSION
from .contracts import AuthoritativeFact, EntityView, RetrievalCandidate
from .database import Database
from .errors import DatabaseUnavailableError, NotFoundError


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StoryRepository:
    """The only data-access boundary used by runtime services."""

    def __init__(self, database: Database):
        self.database = database

    def initialize_fixture(self, fixture: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        project_id = fixture["project"]["project_id"]
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                previous = conn.execute(
                    "SELECT result_json FROM idempotency_ledger WHERE project_id=? AND idempotency_key=?",
                    (project_id, idempotency_key),
                ).fetchone()
                if previous:
                    conn.rollback()
                    result = json.loads(previous[0])
                    result["replayed"] = True
                    return result
                now = _now()
                project = fixture["project"]
                conn.execute(
                    "INSERT OR IGNORE INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        project_id,
                        int(project.get("revision", 1)),
                        project.get("phase", "drafting"),
                        int(project.get("latest_chapter", 0)),
                        SCHEMA_VERSION,
                        now,
                        now,
                        project.get("authority_mode", "legacy"),
                    ),
                )
                for row in fixture.get("entities", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO entities VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (project_id, row["entity_id"], row["entity_type"], row["canonical_name"], _json(row.get("aliases", [])), _json(row.get("attributes", {})), _json(row.get("history", []))),
                    )
                for row in fixture.get("relationships", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO relationships VALUES (?, ?, ?, ?, ?, ?)",
                        (project_id, row["relationship_id"], row["source_entity_id"], row["target_entity_id"], row["relationship_type"], _json(row.get("attributes", {}))),
                    )
                for row in fixture.get("events", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO story_events(project_id,event_id,event_type,subject,chapter_number,payload_json,evidence_json,confidence) VALUES (?,?,?,?,?,?,?,?)",
                        (project_id, row["event_id"], row["event_type"], row["subject"], row.get("chapter_number"), _json(row.get("payload", {})), _json(row.get("evidence", [])), float(row.get("confidence", 1.0))),
                    )
                for row in fixture.get("timeline", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO timeline VALUES (?, ?, ?, ?, ?, ?)",
                        (project_id, row["timeline_id"], row["sequence_key"], row["title"], row.get("event_id"), _json(row.get("details", {}))),
                    )
                for row in fixture.get("narrative_threads", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO narrative_threads VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (project_id, row["thread_id"], row["title"], row["status"], row["introduced_chapter"], row.get("resolved_chapter"), _json(row.get("details", {}))),
                    )
                for row in fixture.get("chapter_summaries", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO chapter_summaries VALUES (?, ?, ?, ?, ?)",
                        (project_id, row["chapter_number"], row["title"], row["summary"], row.get("body_sha256")),
                    )
                for row in fixture.get("facts", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO facts VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (project_id, row["fact_id"], row["subject"], row["predicate"], _json(row.get("value")), int(row.get("valid_from_revision", 0)), row.get("valid_to_revision")),
                    )
                for row in fixture.get("retrieval_documents", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO retrieval_documents(project_id,source_id,source_type,chapter_number,text) VALUES (?,?,?,?,?)",
                        (project_id, row["source_id"], row["source_type"], row.get("chapter_number"), row["text"]),
                    )
                for name in ("entities", "relationships", "timeline", "threads", "summaries"):
                    conn.execute(
                        "INSERT OR IGNORE INTO projection_checkpoints(project_id,projection_name,status,checkpoint,retry_count,last_error,updated_at,applied_revision,event_offset) VALUES (?, ?, 'ready', ?, 0, NULL, ?, ?, 0)",
                        (project_id, name, int(project.get("revision", 1)), now, int(project.get("revision", 1))),
                    )
                result = {"project_id": project_id, "status": "initialized", "replayed": False}
                conn.execute(
                    "INSERT INTO idempotency_ledger(project_id,idempotency_key,operation,result_json,created_at) VALUES (?, ?, 'fixture.initialize', ?, ?)",
                    (project_id, idempotency_key, _json(result), now),
                )
                conn.commit()
                return result
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise DatabaseUnavailableError("DATABASE_LOCKED", "SQLite is locked; retry after the active transaction ends", retryable=True, details={"repair": "retry"}) from exc
            raise

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.database.connect() as conn:
            row = conn.execute("SELECT project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode,runtime_finalized_at FROM projects WHERE project_id=?", (project_id,)).fetchone()
            if not row:
                raise NotFoundError("PROJECT_NOT_FOUND", f"project not found: {project_id}")
            return dict(row)

    def get_entity(self, project_id: str, entity_id: str, include_history: bool = False) -> EntityView:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM entities WHERE project_id=? AND entity_id=?", (project_id, entity_id)).fetchone()
            if not row:
                raise NotFoundError("ENTITY_NOT_FOUND", f"entity not found: {entity_id}")
            return EntityView(
                entity_id=row["entity_id"], entity_type=row["entity_type"], canonical_name=row["canonical_name"],
                aliases=json.loads(row["aliases_json"]), attributes=json.loads(row["attributes_json"]),
                history=json.loads(row["history_json"]) if include_history else [],
            )

    def query_facts(self, project_id: str, intent: str, entity_ids: list[str], limit: int) -> list[AuthoritativeFact]:
        terms = [term.casefold() for term in re.findall(r"[\w\u3400-\u9fff]+", intent) if len(term) > 1]
        with self.database.connect() as conn:
            clauses = []
            params: list[Any] = [project_id]
            if entity_ids:
                clauses.append(f"f.subject IN ({','.join('?' for _ in entity_ids)})")
                params.extend(entity_ids)
            if terms:
                clauses.extend("LOWER(f.subject || ' ' || f.predicate || ' ' || f.value_json) LIKE ?" for _ in terms)
                params.extend(f"%{term}%" for term in terms)
            candidate_filter = " AND (" + " OR ".join(clauses) + ")" if clauses else ""
            params.append(max(limit * 20, limit))
            rows = conn.execute(
                "SELECT f.*,p.updated_at FROM facts f JOIN projects p USING(project_id) "
                "WHERE f.project_id=? AND valid_to_revision IS NULL" + candidate_filter +
                " ORDER BY f.fact_id LIMIT ?", params,
            ).fetchall()
        ranked = []
        for row in rows:
            haystack = f"{row['subject']} {row['predicate']} {row['value_json']}".casefold()
            exact_entity = row["subject"] in entity_ids
            score = (100 if exact_entity else 0) + sum(1 for term in terms if term in haystack)
            if entity_ids and not exact_entity and score == 0:
                continue
            ranked.append((score, row))
        ranked.sort(key=lambda item: (-item[0], item[1]["fact_id"]))
        return [
            AuthoritativeFact(
                fact_id=row["fact_id"], subject=row["subject"], predicate=row["predicate"], value=json.loads(row["value_json"]),
                valid_from_revision=row["valid_from_revision"], valid_to_revision=row["valid_to_revision"],
                source=f"fact:{row['fact_id']}", confidence=1.0, updated_at=row["updated_at"],
            )
            for _, row in ranked[:limit]
        ]

    def rag_search(self, project_id: str, query: str, limit: int) -> list[RetrievalCandidate]:
        terms = [term.casefold() for term in re.findall(r"[\w\u3400-\u9fff]+", query) if len(term) > 1]
        if not terms or limit <= 0:
            return []
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT d.source_id,d.text,p.updated_at,bm25(retrieval_fts_trigram) AS rank FROM retrieval_fts_trigram "
                "JOIN retrieval_documents d ON d.row_id=retrieval_fts_trigram.rowid "
                "JOIN projects p ON p.project_id=d.project_id "
                "WHERE retrieval_fts_trigram MATCH ? AND d.project_id=? ORDER BY rank,d.source_id LIMIT ?",
                (match, project_id, max(limit * 10, limit)),
            ).fetchall()
        scored = []
        for row in rows:
            text = row["text"].casefold()
            overlap = sum(text.count(term) for term in terms)
            if overlap:
                score = overlap / max(1.0, len(terms))
                scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], item[1]["source_id"]))
        return [RetrievalCandidate(source_id=row["source_id"], text=row["text"], score=round(score, 6), updated_at=row["updated_at"]) for score, row in scored[:limit]]

    def active_fact_conflicts(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            keys = conn.execute(
                "SELECT subject,predicate FROM facts WHERE project_id=? AND valid_to_revision IS NULL "
                "GROUP BY subject,predicate HAVING COUNT(DISTINCT value_json)>1 ORDER BY subject,predicate",
                (project_id,),
            ).fetchall()
            conflicts = []
            for key in keys:
                group = conn.execute(
                    "SELECT fact_id,value_json FROM facts WHERE project_id=? AND subject=? AND predicate=? "
                    "AND valid_to_revision IS NULL ORDER BY fact_id",
                    (project_id, key["subject"], key["predicate"]),
                ).fetchall()
                values = [json.loads(row["value_json"]) for row in group]
                conflicts.append({
                    "subject": key["subject"],
                    "predicate": key["predicate"],
                    "item_ids": [row["fact_id"] for row in group],
                    "values": values,
                })
        return conflicts

    def recent_chapter_summaries(self, project_id: str, before_chapter: int, limit: int = 5) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT chapter_number,title,summary FROM chapter_summaries "
                "WHERE project_id=? AND chapter_number<? ORDER BY chapter_number DESC LIMIT ?",
                (project_id, before_chapter, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_timeline_entry(self, project_id: str) -> dict[str, Any] | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT timeline_id,sequence_key,title,details_json FROM timeline "
                "WHERE project_id=? ORDER BY sequence_key DESC,timeline_id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return {**dict(row), "details": json.loads(row["details_json"])} if row else None

    def recent_narrative_documents(self, project_id: str, before_chapter: int, limit: int = 3) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            latest = conn.execute(
                "SELECT MAX(chapter_number) FROM retrieval_documents WHERE project_id=? AND chapter_number<?",
                (project_id, before_chapter),
            ).fetchone()[0]
            if latest is None:
                return []
            rows = conn.execute(
                "SELECT d.source_id,d.text,d.chapter_number,p.updated_at FROM retrieval_documents d "
                "JOIN projects p USING(project_id) WHERE d.project_id=? AND d.chapter_number=? "
                "ORDER BY d.source_id DESC LIMIT ?",
                (project_id, latest, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def active_narrative_threads(self, project_id: str, limit: int = 25) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT thread_id,title,status,introduced_chapter,resolved_chapter,details_json "
                "FROM narrative_threads WHERE project_id=? AND resolved_chapter IS NULL "
                "ORDER BY introduced_chapter,thread_id LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]

    def projection_health(self, project_id: str) -> dict[str, Any]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT projection_name,status,checkpoint,retry_count,last_error FROM projection_checkpoints WHERE project_id=? ORDER BY projection_name", (project_id,)).fetchall()
        states = [dict(row) for row in rows]
        degraded = [row for row in states if row["status"] != "ready"]
        return {"status": "degraded" if degraded else "ready", "recoverable": all(row["status"] in {"ready", "retryable"} for row in states), "projections": states}

    def record_projection_failure(self, project_id: str, projection_name: str, message: str) -> None:
        with self.database.connect() as conn:
            now = _now()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO projection_checkpoints(project_id,projection_name,status,checkpoint,retry_count,last_error,updated_at) VALUES (?,?,'retryable',0,1,?,?) ON CONFLICT(project_id,projection_name) DO UPDATE SET status='retryable',retry_count=retry_count+1,last_error=excluded.last_error,updated_at=excluded.updated_at",
                (project_id, projection_name, message, now),
            )
            conn.execute(
                "INSERT INTO runtime_incidents(project_id,component,state,message,retryable,repair_action,created_at) VALUES (?,?,'degraded',?,1,'replay projection',?)",
                (project_id, projection_name, message, now),
            )
            conn.commit()

    def unresolved_incidents(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT component,state,message,retryable,repair_action FROM runtime_incidents WHERE project_id=? AND resolved_at IS NULL ORDER BY incident_id", (project_id,))]

    def integrity_check(self) -> str:
        with self.database.connect() as conn:
            return str(conn.execute("PRAGMA integrity_check").fetchone()[0])

    def counts(self, project_id: str) -> dict[str, int]:
        result = {}
        with self.database.connect() as conn:
            for public_name, table in {
                "characters": "entities", "relationships": "relationships", "events": "story_events",
                "timeline": "timeline", "narrative_threads": "narrative_threads", "chapter_summaries": "chapter_summaries",
            }.items():
                result[public_name] = int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)).fetchone()[0])
        return result
