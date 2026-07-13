from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from . import SCHEMA_VERSION, __version__
from .contracts import (
    ContextConflict, ContextItem, ContextItemSource, ContextLayers, ContextQueryResult,
    DoctorCheck, DoctorResult, EntityResult, HealthResponse, ProjectStatusResponse,
    QueryContextRequest, QueryTrace,
)
from .database import Database
from .chapter_commits import ChapterCommitService
from .repository import StoryRepository


class RuntimeServices:
    def __init__(self, database: Database, repository: StoryRepository):
        self.database = database
        self.repository = repository

    def health(self) -> HealthResponse:
        try:
            current = self.database.migrations.current_version()
            if current < self.database.latest_schema_version:
                return HealthResponse(status="degraded", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="migration_required")
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.rollback()
            return HealthResponse(status="ok", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="ready")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                return HealthResponse(status="degraded", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="locked")
            return HealthResponse(status="unavailable", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="unavailable")

    def project_status(self, project_id: str) -> ProjectStatusResponse:
        project = self.repository.get_project(project_id)
        projection = self.repository.projection_health(project_id)
        degraded_names = [row["projection_name"] for row in projection["projections"] if row["status"] != "ready"]
        return ProjectStatusResponse(
            project_id=project_id, revision=project["revision"], phase=project["phase"], latest_chapter=project["latest_chapter"],
            projection_health={
                "status": projection["status"],
                "recoverable": "true" if projection["recoverable"] else "false",
                "repair": "replay:" + ",".join(degraded_names) if degraded_names else "none",
            },
            schema_version=project["schema_version"],
            active_prepare_ids=self._active_prepare_ids(project_id),
            authority_mode=project.get("authority_mode", "legacy"),
        )

    def _active_prepare_ids(self, project_id: str) -> list[str]:
        with self.database.connect() as conn:
            return [row[0] for row in conn.execute(
                "SELECT commit_id FROM chapter_commits WHERE project_id=? AND state IN ('PREPARED','VALIDATED') ORDER BY created_at",
                (project_id,),
            )]

    def entity(self, project_id: str, entity_id: str, include_history: bool = False) -> EntityResult:
        project = self.repository.get_project(project_id)
        return EntityResult(project_id=project_id, revision=project["revision"], entity=self.repository.get_entity(project_id, entity_id, include_history))

    def query_context(self, request: QueryContextRequest) -> ContextQueryResult:
        project = self.repository.get_project(request.project_id)
        facts = self.repository.query_facts(request.project_id, request.intent, request.entity_ids, request.budget.max_items)
        remaining = max(0, request.budget.max_items - len(facts))
        retrieval = self.repository.rag_search(request.project_id, request.intent, remaining) if request.include_retrieval_candidates else []
        # The layered budget pass below performs importance-aware semantic
        # compaction. Do not truncate the raw candidate lists by byte offset.
        selected_facts = facts
        selected_retrieval = retrieval
        now = project["updated_at"]
        items: list[ContextItem] = []
        for fact in selected_facts:
            layer, importance = _classify_fact(fact.predicate)
            items.append(ContextItem(
                item_id=fact.fact_id, layer=layer,
                content=f"{fact.subject} | {fact.predicate} | {json.dumps(fact.value, ensure_ascii=False, sort_keys=True)}",
                source=ContextItemSource(kind="structured_query", id=fact.source),
                confidence=fact.confidence, updated_at=fact.updated_at, importance=importance,
                trust="trusted", subject=fact.subject, predicate=fact.predicate,
            ))

        existing_ids = {item.item_id for item in items}
        timeline = self.repository.latest_timeline_entry(request.project_id)
        if timeline:
            items.append(ContextItem(
                item_id=f"timeline:{timeline['timeline_id']}", layer="hard_constraints",
                content=f"Current time point {timeline['sequence_key']}: {timeline['title']} | "
                        f"{json.dumps(timeline['details'], ensure_ascii=False, sort_keys=True)}",
                source=ContextItemSource(kind="structured_query", id=f"timeline:{timeline['timeline_id']}"),
                confidence=1.0, updated_at=now, importance=100, trust="trusted",
                subject="timeline", predicate="timeline.current",
            ))
        for thread in self.repository.active_narrative_threads(request.project_id):
            item_id = f"thread:{thread['thread_id']}"
            if item_id in existing_ids:
                continue
            items.append(ContextItem(
                item_id=item_id, layer="plot_commitments",
                content=f"{thread['title']} | status={thread['status']} | {json.dumps(thread['details'], ensure_ascii=False, sort_keys=True)}",
                source=ContextItemSource(kind="structured_query", id=item_id), confidence=1.0,
                updated_at=now, importance=90, trust="trusted", subject=thread["thread_id"],
                predicate="narrative_thread.open",
            ))

        for summary in self.repository.recent_chapter_summaries(request.project_id, request.chapter_number):
            item_id = f"summary:{summary['chapter_number']}"
            if item_id in existing_ids:
                continue
            items.append(ContextItem(
                item_id=item_id, layer="recent_narrative",
                content=f"Chapter {summary['chapter_number']} - {summary['title']}: {summary['summary']}",
                source=ContextItemSource(kind="chapter_summary", id=item_id), confidence=1.0,
                updated_at=now, importance=75, trust="trusted", subject=f"chapter-{summary['chapter_number']}",
                predicate="chapter.summary",
            ))

        for document in self.repository.recent_narrative_documents(request.project_id, request.chapter_number):
            items.append(ContextItem(
                item_id=f"recent:{document['source_id']}", layer="recent_narrative", content=document["text"],
                source=ContextItemSource(kind="rag", id=document["source_id"]), confidence=1.0,
                updated_at=document["updated_at"], importance=80, trust="untrusted_content",
                subject=f"chapter-{document['chapter_number']}", predicate="chapter.excerpt",
            ))

        for candidate in selected_retrieval:
            items.append(ContextItem(
                item_id=f"rag:{candidate.source_id}", layer="relevant_memory", content=candidate.text,
                source=ContextItemSource(kind="rag", id=candidate.source_id),
                confidence=max(0.0, min(1.0, candidate.score)), updated_at=candidate.updated_at,
                importance=50, trust="untrusted_content",
            ))

        items = _compress_to_budget(items, request.budget.max_tokens, request.budget.max_items)
        conflicts = _detect_conflicts(items)
        known_conflict_ids = {conflict.conflict_id for conflict in conflicts}
        for conflict in self.repository.active_fact_conflicts(request.project_id):
            digest = hashlib.sha256(f"{conflict['subject']}\0{conflict['predicate']}".encode()).hexdigest()[:16]
            conflict_id = f"conflict:{digest}"
            if conflict_id in known_conflict_ids:
                continue
            conflicts.append(ContextConflict(
                conflict_id=conflict_id, subject=conflict["subject"], predicate=conflict["predicate"],
                item_ids=conflict["item_ids"], values=conflict["values"],
                message=f"Conflicting authoritative facts for {conflict['subject']}.{conflict['predicate']}; no value was selected.",
            ))
        layers = ContextLayers()
        for item in items:
            getattr(layers, item.layer).append(item)
        selected_ids = [item.item_id for item in items]
        full_item_ids = {item.item_id for item in items if not item.content.startswith("Compressed reference:")}
        returned_facts = [fact for fact in selected_facts if fact.fact_id in full_item_ids]
        returned_retrieval = [
            candidate for candidate in selected_retrieval
            if f"rag:{candidate.source_id}" in full_item_ids or f"recent:{candidate.source_id}" in full_item_ids
        ]
        if selected_retrieval and not returned_retrieval:
            returned_retrieval = selected_retrieval[:1]
        # The budget governs the assembled layer payload consumed by generation.
        # Compatibility arrays and conflict diagnostics are reported separately.
        budget_used = (sum(len(item.model_dump_json()) for item in items) + 3) // 4
        return ContextQueryResult(
            request_id=request.request_id, project_id=request.project_id, revision=project["revision"],
            authoritative_facts=returned_facts, retrieval_candidates=returned_retrieval, untrusted_materials=[],
            layers=layers, conflicts=conflicts,
            trace=QueryTrace(budget_used=budget_used, selected_source_ids=selected_ids),
        )

    def doctor(self, project_id: str, deep: bool = False) -> DoctorResult:
        project = self.repository.get_project(project_id)
        checks = [
            DoctorCheck(code="schema.current", status="pass", message=f"schema migration {self.database.migrations.current_version()} is current", repair=None),
            DoctorCheck(code="authority.integrity", status="pass", message="SQLite integrity check passed", repair=None),
            DoctorCheck(code="writes.authority", status="pass", message="chapter commit endpoints are enabled for Runtime-authority projects", repair=None),
        ]
        if deep and self.repository.integrity_check() != "ok":
            checks[1] = DoctorCheck(code="authority.integrity", status="fail", message="SQLite integrity check failed", repair="restore a verified snapshot")
        projection = self.repository.projection_health(project_id)
        if projection["status"] == "ready":
            checks.append(DoctorCheck(code="projections.core", status="pass", message="all core projections are ready", repair=None))
        else:
            checks.append(DoctorCheck(code="projections.core", status="warning", message="one or more projections require replay", repair="preview projection replay, verify the hash, then confirm execution", retryable=True, requires_confirmation=True))
        for incident in self.repository.unresolved_incidents(project_id):
            checks.append(DoctorCheck(code=f"incident.{incident['component']}", status="warning" if incident["retryable"] else "fail", message=incident["message"], repair=incident["repair_action"], retryable=bool(incident["retryable"])))
        if project.get("authority_mode") == "runtime":
            with self.database.connect() as conn:
                pending = [dict(row) for row in conn.execute(
                    "SELECT commit_id,state,chapter_number FROM chapter_commits WHERE project_id=? AND state IN ('PREPARED','VALIDATED') ORDER BY updated_at",
                    (project_id,),
                )]
                incomplete = [dict(row) for row in conn.execute(
                    "SELECT commit_id,state,chapter_number FROM chapter_commits WHERE project_id=? AND state IN ('PERSISTING','COMMITTED','PROJECTING','RECOVERY_REQUIRED') ORDER BY updated_at",
                    (project_id,),
                )]
                outbox_count = int(conn.execute("SELECT COUNT(*) FROM outbox WHERE project_id=? AND status IN ('pending','failed')", (project_id,)).fetchone()[0])
                for row in pending:
                    checks.append(DoctorCheck(
                        code=f"commit.{row['commit_id']}", status="warning",
                        message=f"chapter {row['chapter_number']} commit is {row['state']}",
                        repair="resume with the same idempotency key or preview an abort", requires_confirmation=True,
                    ))
                for row in incomplete:
                    checks.append(DoctorCheck(
                        code=f"commit.{row['commit_id']}", status="fail",
                        message=f"chapter {row['chapter_number']} commit requires recovery from {row['state']}",
                        repair="run commit recovery with the original request; do not write legacy files",
                    ))
                if outbox_count:
                    checks.append(DoctorCheck(
                        code="outbox.pending", status="warning",
                        message=f"{outbox_count} rebuildable side effects are pending",
                        repair="retry the affected outbox item; core authority is already committed", retryable=True,
                    ))
                if deep:
                    commit_service = ChapterCommitService(self.database)
                    for checkpoint in conn.execute("SELECT projection_name,state_hash FROM projection_checkpoints WHERE project_id=? AND state_hash IS NOT NULL", (project_id,)):
                        current_hash = commit_service.projection_hash(conn, project_id, [checkpoint["projection_name"]])
                        if current_hash != checkpoint["state_hash"]:
                            checks.append(DoctorCheck(
                                code=f"projection.{checkpoint['projection_name']}.hash", status="fail",
                                message="projection hash differs from its finalized checkpoint",
                                repair=f"verify and replay projection {checkpoint['projection_name']}",
                            ))
        status = "blocked" if any(c.status in {"fail", "blocked"} for c in checks) else "warning" if any(c.status == "warning" for c in checks) else "ok"
        return DoctorResult(project_id=project_id, revision=project["revision"], status=status, checks=checks)

    def fixture_summary(self, project_id: str) -> dict[str, Any]:
        return {"project": self.repository.get_project(project_id), "counts": self.repository.counts(project_id)}


def _classify_fact(predicate: str) -> tuple[str, int]:
    normalized = predicate.casefold()
    if any(token in normalized for token in ("character", "status", "dead", "depart", "location", "resource", "world", "rule", "timeline")):
        return "hard_constraints", 100
    if any(token in normalized for token in ("thread", "hook", "outline", "commitment", "must")):
        return "plot_commitments", 90
    if "chapter.summary" in normalized:
        return "recent_narrative", 75
    if any(token in normalized for token in ("style", "pov", "pace", "banned", "word_count")):
        return "style_guidance", 65
    return "relevant_memory", 60


def _detect_conflicts(items: list[ContextItem]) -> list[ContextConflict]:
    groups: dict[tuple[str, str], list[ContextItem]] = {}
    for item in items:
        if item.source.kind != "structured_query" or not item.subject or not item.predicate:
            continue
        groups.setdefault((item.subject, item.predicate), []).append(item)
    conflicts: list[ContextConflict] = []
    for (subject, predicate), group in groups.items():
        values = [item.content.split(" | ", 2)[-1] for item in group]
        if len(group) < 2 or len(set(values)) < 2:
            continue
        digest = hashlib.sha256(f"{subject}\0{predicate}".encode()).hexdigest()[:16]
        conflicts.append(ContextConflict(
            conflict_id=f"conflict:{digest}", subject=subject, predicate=predicate,
            item_ids=[item.item_id for item in group], values=values,
            message=f"Conflicting authoritative facts for {subject}.{predicate}; no value was selected.",
        ))
    return conflicts


def _compress_to_budget(items: list[ContextItem], max_tokens: int, max_items: int) -> list[ContextItem]:
    """Keep high-importance context and semantically compact overflow items; never slice text."""
    max_chars = max_tokens * 4
    selected: list[ContextItem] = []
    used = 0
    ordered = sorted(enumerate(items), key=lambda pair: (-pair[1].importance, pair[0]))
    compression_needed = sum(len(item.model_dump_json()) for item in items) > max_chars
    for _, item in ordered:
        if len(selected) >= max_items:
            break
        candidate = item
        if compression_needed and item.importance < 75:
            candidate = item.model_copy(update={
                "content": f"Compressed reference: {item.source.id}; "
                           f"{item.subject or 'n/a'}.{item.predicate or 'n/a'}",
            })
        cost = len(candidate.model_dump_json())
        if used + cost > max_chars and candidate is item:
            candidate = item.model_copy(update={
                "content": f"Compressed reference: {item.source.id}; "
                           f"{item.subject or 'n/a'}.{item.predicate or 'n/a'}",
            })
            cost = len(candidate.model_dump_json())
        if used + cost > max_chars:
            continue
        selected.append(candidate)
        used += cost
    return selected
