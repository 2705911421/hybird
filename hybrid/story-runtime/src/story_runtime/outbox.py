from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable

from .contracts import OutboxRunRequest, OutboxRunResult
from .database import Database
from .errors import ConflictError, DatabaseUnavailableError


class OutboxWorker:
    """Executes disposable projections without participating in authority writes."""

    def __init__(self, database: Database, fault_injector: Callable[[str], None] | None = None):
        self.database = database
        self.fault_injector = fault_injector
        self.root = database.config.projection_root or database.path.parent / "projections"

    def run(self, request: OutboxRunRequest) -> OutboxRunResult:
        if request.admin_scope != "story-runtime.outbox.run":
            raise ConflictError("OPERATOR_SCOPE_REQUIRED", "outbox execution requires operator scope")
        completed = failed = claimed = 0
        after_id = 0
        for _ in range(request.limit):
            row = self._claim(request.project_id, request.retry_failed, after_id)
            if row is None:
                break
            after_id = int(row["outbox_id"])
            claimed += 1
            try:
                self._inject("outbox.before_execute")
                self._execute(row)
                self._finish(row["outbox_id"], "done", None)
                completed += 1
            except Exception as exc:  # the durable row is the retry boundary
                self._finish(row["outbox_id"], "failed", str(exc))
                failed += 1
        with self.database.connect() as conn:
            params: tuple[Any, ...] = (request.project_id,) if request.project_id else ()
            where = " AND project_id=?" if request.project_id else ""
            pending = int(conn.execute(
                f"SELECT COUNT(*) FROM outbox WHERE status IN ('pending','failed'){where}", params
            ).fetchone()[0])
        return OutboxRunResult(
            request_id=request.request_id, claimed=claimed, completed=completed,
            failed=failed, pending=pending,
        )

    def _claim(self, project_id: str | None, retry_failed: bool, after_id: int) -> sqlite3.Row | None:
        statuses = "('pending','failed')" if retry_failed else "('pending')"
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                params: tuple[Any, ...] = (after_id, project_id) if project_id else (after_id,)
                where = " AND project_id=?" if project_id else ""
                row = conn.execute(
                    f"SELECT * FROM outbox WHERE status IN {statuses} AND outbox_id>?{where} ORDER BY outbox_id LIMIT 1", params
                ).fetchone()
                if row is None:
                    conn.rollback()
                    return None
                conn.execute(
                    "UPDATE outbox SET status='processing',updated_at=datetime('now') WHERE outbox_id=?",
                    (row["outbox_id"],),
                )
                conn.commit()
                return row
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise DatabaseUnavailableError("DATABASE_LOCKED", "SQLite is locked; retry outbox execution", retryable=True) from exc
            raise

    def _execute(self, row: sqlite3.Row) -> None:
        topic = row["topic"]
        payload = json.loads(row["payload_json"])
        if topic == "search.index":
            self._update_search_index(row["project_id"], int(payload.get("chapter_number", 0)))
            return
        if topic == "markdown.export":
            self._export_markdown(row["project_id"], int(payload["chapter_number"]))
            return
        if topic == "snapshot.create":
            self._export_snapshot(row["project_id"], int(payload["revision"]))
            return
        raise ValueError(f"unsupported outbox topic: {topic}")

    def _update_search_index(self, project_id: str, chapter_number: int) -> None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT title,body_text FROM chapter_artifacts a JOIN chapter_commits c USING(commit_id) "
                "WHERE a.project_id=? AND a.chapter_number=? AND c.state='FINALIZED'",
                (project_id, chapter_number),
            ).fetchone()
            if row is None:
                raise ValueError("finalized chapter is unavailable for search projection")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO retrieval_documents(project_id,source_id,source_type,chapter_number,text) VALUES (?,?,?,?,?) "
                "ON CONFLICT(project_id,source_id) DO UPDATE SET text=excluded.text,chapter_number=excluded.chapter_number",
                (project_id, f"chapter:{chapter_number}", "chapter", chapter_number, f"{row['title']}\n\n{row['body_text']}"),
            )
            conn.commit()

    def _export_markdown(self, project_id: str, chapter_number: int) -> None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT a.title,a.body_text,a.body_sha256 FROM chapter_artifacts a JOIN chapter_commits c USING(commit_id) "
                "WHERE a.project_id=? AND a.chapter_number=? AND c.state='FINALIZED'",
                (project_id, chapter_number),
            ).fetchone()
        if row is None:
            raise ValueError("finalized chapter is unavailable for Markdown export")
        content = f"<!-- non-authoritative projection; sha256={row['body_sha256']} -->\n# {row['title']}\n\n{row['body_text']}\n"
        self._atomic_write(self._project_dir(project_id) / "chapters" / f"{chapter_number:04d}.md", content.encode("utf-8"))

    def _export_snapshot(self, project_id: str, revision: int) -> None:
        with self.database.connect() as conn:
            project = dict(conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone())
            commits = [dict(row) for row in conn.execute(
                "SELECT commit_id,chapter_number,resulting_revision,body_sha256,artifact_sha256,finalized_at "
                "FROM chapter_commits WHERE project_id=? AND state='FINALIZED' ORDER BY chapter_number", (project_id,)
            )]
        payload = {"kind": "non-authoritative-snapshot", "revision": revision, "project": project, "commits": commits}
        self._atomic_write(
            self._project_dir(project_id) / "snapshots" / f"revision-{revision}.json",
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
        )

    def _project_dir(self, project_id: str) -> Path:
        if not project_id or project_id in {".", ".."} or any(char in project_id for char in "/\\:"):
            raise ValueError("unsafe project id for projection path")
        return self.root / project_id

    def _atomic_write(self, target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            temporary.write_bytes(content)
            self._inject("outbox.before_replace")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _finish(self, outbox_id: int, status: str, error: str | None) -> None:
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE outbox SET status=?,retry_count=retry_count+?,last_error=?,updated_at=datetime('now') WHERE outbox_id=?",
                (status, int(status == "failed"), error, outbox_id),
            )
            conn.commit()

    def _inject(self, point: str) -> None:
        if self.fault_injector:
            self.fault_injector(point)
