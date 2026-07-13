from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .contracts import (
    ChapterAggregateItem,
    ChapterAggregateResult,
    ChapterCollectionResult,
    ChapterExportItem,
    ChapterExportRequest,
    ChapterExportSnapshotResult,
    ChapterListItem,
    ChapterSearchHit,
    ChapterSearchResult,
    PageInfo,
    VolumeAggregate,
)
from .database import Database
from .errors import ConflictError, DatabaseUnavailableError, NotFoundError


_FINALIZED_SELECT = """
SELECT c.commit_id,c.chapter_number,c.resulting_revision,c.body_sha256,
       c.artifact_sha256,c.created_at,c.updated_at,c.finalized_at,
       a.title,a.body_text,a.summary,
       CAST(json_extract(a.outline_fulfillment_json,'$.volume_id') AS TEXT) AS volume_id,
       length(a.body_text) AS character_count
FROM chapter_commits c
JOIN chapter_artifacts a USING(commit_id)
WHERE c.project_id=? AND c.state='FINALIZED'
"""


def _cursor(revision: int, chapter_number: int) -> str:
    raw = json.dumps({"revision": revision, "chapter": chapter_number}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None, revision: int) -> int:
    if value is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded = json.loads(raw.decode("utf-8"))
        cursor_revision = int(decoded["revision"])
        chapter = int(decoded["chapter"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ConflictError("INVALID_CURSOR", "chapter cursor is malformed") from exc
    if cursor_revision != revision:
        raise ConflictError(
            "REVISION_CHANGED",
            "project revision changed while reading chapters; restart pagination",
            current_revision=revision,
            details={"cursor_revision": cursor_revision},
        )
    if chapter < 0:
        raise ConflictError("INVALID_CURSOR", "chapter cursor is malformed")
    return chapter


def _filters(
    *,
    after_chapter: int = 0,
    from_chapter: int | None = None,
    to_chapter: int | None = None,
    volume_id: str | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["c.chapter_number>?"]
    params: list[Any] = [after_chapter]
    if from_chapter is not None:
        clauses.append("c.chapter_number>=?")
        params.append(from_chapter)
    if to_chapter is not None:
        clauses.append("c.chapter_number<=?")
        params.append(to_chapter)
    if volume_id is not None:
        clauses.append("CAST(json_extract(a.outline_fulfillment_json,'$.volume_id') AS TEXT)=?")
        params.append(volume_id)
    return " AND " + " AND ".join(clauses), params


def _metadata(row: sqlite3.Row) -> ChapterListItem:
    return ChapterListItem(
        chapter_id=row["commit_id"],
        chapter_number=row["chapter_number"],
        order_key=row["chapter_number"],
        title=row["title"],
        summary=row["summary"],
        body_sha256=row["body_sha256"],
        artifact_sha256=row["artifact_sha256"],
        character_count=row["character_count"],
        commit_id=row["commit_id"],
        resulting_revision=row["resulting_revision"],
        volume_id=row["volume_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finalized_at=row["finalized_at"],
    )


def _export_item(row: sqlite3.Row) -> ChapterExportItem:
    actual = hashlib.sha256(row["body_text"].encode("utf-8")).hexdigest()
    if actual != row["body_sha256"]:
        raise DatabaseUnavailableError(
            "CHAPTER_CHECKSUM_MISMATCH",
            f"chapter {row['chapter_number']} body checksum does not match Runtime metadata",
            details={"chapter_number": row["chapter_number"]},
        )
    return ChapterExportItem(**_metadata(row).model_dump(), body=row["body_text"])


class ChapterReadService:
    """Product-level finalized chapter read model backed only by Runtime authority."""

    def __init__(self, database: Database):
        self.database = database

    def collection(
        self,
        project_id: str,
        *,
        cursor: str | None,
        limit: int,
        from_chapter: int | None,
        to_chapter: int | None,
        volume_id: str | None,
        finalized_only: bool,
    ) -> ChapterCollectionResult:
        self._require_finalized(finalized_only)
        self._validate_range(from_chapter, to_chapter)
        try:
            with self.database.read() as conn:
                conn.execute("BEGIN")
                project = self._project(conn, project_id)
                revision = int(project["revision"])
                after = _decode_cursor(cursor, revision)
                where, params = _filters(
                    after_chapter=after,
                    from_chapter=from_chapter,
                    to_chapter=to_chapter,
                    volume_id=volume_id,
                )
                count_where, count_params = _filters(
                    from_chapter=from_chapter,
                    to_chapter=to_chapter,
                    volume_id=volume_id,
                )
                total = conn.execute(
                    "SELECT count(*) FROM chapter_commits c JOIN chapter_artifacts a USING(commit_id) "
                    "WHERE c.project_id=? AND c.state='FINALIZED'" + count_where,
                    [project_id, *count_params],
                ).fetchone()[0]
                rows = conn.execute(
                    _FINALIZED_SELECT + where + " ORDER BY c.chapter_number ASC LIMIT ?",
                    [project_id, *params, limit + 1],
                ).fetchall()
                conn.commit()
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)
        has_more = len(rows) > limit
        visible = rows[:limit]
        items = [_metadata(row) for row in visible]
        next_cursor = _cursor(revision, items[-1].chapter_number) if has_more and items else None
        return ChapterCollectionResult(
            project_id=project_id,
            revision=revision,
            total_count=total,
            latest_chapter=project["latest_chapter"],
            items=items,
            page=PageInfo(limit=limit, has_more=has_more, next_cursor=next_cursor),
        )

    def aggregate(self, project_id: str) -> ChapterAggregateResult:
        try:
            with self.database.read() as conn:
                conn.execute("BEGIN")
                project = self._project(conn, project_id)
                rows = conn.execute(
                    _FINALIZED_SELECT + " ORDER BY c.chapter_number ASC", (project_id,)
                ).fetchall()
                conn.commit()
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)
        volumes: dict[str, tuple[int, int]] = {}
        chapters = []
        for row in rows:
            chapters.append(ChapterAggregateItem(
                chapter_number=row["chapter_number"],
                character_count=row["character_count"],
                volume_id=row["volume_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                finalized_at=row["finalized_at"],
            ))
            if row["volume_id"] is not None:
                count, characters = volumes.get(row["volume_id"], (0, 0))
                volumes[row["volume_id"]] = (count + 1, characters + row["character_count"])
        return ChapterAggregateResult(
            project_id=project_id,
            revision=project["revision"],
            chapter_count=len(rows),
            latest_chapter=project["latest_chapter"],
            total_characters=sum(row["character_count"] for row in rows),
            chapters=chapters,
            volumes=[VolumeAggregate(volume_id=key, chapter_count=value[0], character_count=value[1]) for key, value in sorted(volumes.items())],
        )

    def export_snapshot(self, project_id: str, request: ChapterExportRequest) -> ChapterExportSnapshotResult:
        self._validate_range(request.from_chapter, request.to_chapter)
        try:
            with self.database.read() as conn:
                conn.execute("BEGIN")
                project = self._project(conn, project_id)
                revision = int(project["revision"])
                if request.expected_revision is not None and request.expected_revision != revision:
                    raise ConflictError(
                        "REVISION_CHANGED",
                        "project revision does not match requested export revision",
                        current_revision=revision,
                        details={"expected_revision": request.expected_revision},
                    )
                where, params = _filters(
                    from_chapter=request.from_chapter,
                    to_chapter=request.to_chapter,
                    volume_id=request.volume_id,
                )
                rows = conn.execute(
                    _FINALIZED_SELECT + where + " ORDER BY c.chapter_number ASC",
                    [project_id, *params],
                ).fetchall()
                chapters = [_export_item(row) for row in rows]
                conn.commit()
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)
        collection_sha256 = hashlib.sha256(
            "\n".join(f"{item.chapter_number}:{item.body_sha256}" for item in chapters).encode("utf-8")
        ).hexdigest()
        return ChapterExportSnapshotResult(
            snapshot_id=f"{project_id}:{revision}:{collection_sha256[:16]}",
            project_id=project_id,
            revision=revision,
            collection_sha256=collection_sha256,
            chapter_count=len(chapters),
            chapters=chapters,
            created_at=datetime.now(timezone.utc),
        )

    def search(self, project_id: str, query: str, *, cursor: str | None, limit: int) -> ChapterSearchResult:
        normalized = query.strip()
        if not normalized:
            raise ConflictError("EMPTY_SEARCH_QUERY", "chapter search query must not be empty")
        try:
            with self.database.read() as conn:
                conn.execute("BEGIN")
                project = self._project(conn, project_id)
                revision = int(project["revision"])
                after = _decode_cursor(cursor, revision)
                match = "instr(lower(a.title),lower(?))>0 OR instr(lower(a.summary),lower(?))>0 OR instr(lower(a.body_text),lower(?))>0"
                params = [normalized, normalized, normalized]
                total = conn.execute(
                    "SELECT count(*) FROM chapter_commits c JOIN chapter_artifacts a USING(commit_id) "
                    f"WHERE c.project_id=? AND c.state='FINALIZED' AND ({match})",
                    [project_id, *params],
                ).fetchone()[0]
                rows = conn.execute(
                    _FINALIZED_SELECT + f" AND c.chapter_number>? AND ({match}) ORDER BY c.chapter_number ASC LIMIT ?",
                    [project_id, after, *params, limit + 1],
                ).fetchall()
                conn.commit()
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)
        has_more = len(rows) > limit
        visible = rows[:limit]
        items = [ChapterSearchHit(**_export_item(row).model_dump(), snippet=self._snippet(row, normalized)) for row in visible]
        next_cursor = _cursor(revision, items[-1].chapter_number) if has_more and items else None
        return ChapterSearchResult(
            project_id=project_id,
            revision=revision,
            index_revision=revision,
            query=normalized,
            total_count=total,
            items=items,
            page=PageInfo(limit=limit, has_more=has_more, next_cursor=next_cursor),
        )

    @staticmethod
    def _project(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT project_id,revision,latest_chapter FROM projects WHERE project_id=?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("PROJECT_NOT_FOUND", f"project not found: {project_id}")
        return row

    @staticmethod
    def _require_finalized(finalized_only: bool) -> None:
        if not finalized_only:
            raise ConflictError("FINALIZED_ONLY_REQUIRED", "product chapter reads only expose finalized chapters")

    @staticmethod
    def _validate_range(from_chapter: int | None, to_chapter: int | None) -> None:
        if from_chapter is not None and to_chapter is not None and from_chapter > to_chapter:
            raise ConflictError("INVALID_CHAPTER_RANGE", "from_chapter must be less than or equal to to_chapter")

    @staticmethod
    def _snippet(row: sqlite3.Row, query: str) -> str:
        text = row["body_text"]
        position = text.lower().find(query.lower())
        if position < 0:
            return row["summary"][:240] or row["title"]
        start = max(0, position - 80)
        return text[start:position + len(query) + 160]

    @staticmethod
    def _raise_operational(exc: sqlite3.OperationalError) -> None:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise DatabaseUnavailableError(
                "DATABASE_LOCKED", "SQLite is locked; retry the read", retryable=True
            ) from exc
        raise DatabaseUnavailableError(
            "DATABASE_UNAVAILABLE", "Runtime database read failed", retryable=True
        ) from exc
