from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from uuid import UUID

from story_runtime.config import RuntimeConfig
from story_runtime.database import Database


PROJECT_ID = "rc1-verification"
NOW = "2026-07-14T00:00:00+00:00"
CHAPTERS = (
    (1, "第一章：潮声", "第一章：潮声\n\n运行时正文一。", "v1"),
    (2, "第二章：钥匙", "第二章：钥匙\n\n运行时正文二，校验唯一。", "v1"),
    (3, "第三章：灯塔", "第三章：灯塔\n\n运行时正文三。", "v2"),
)


def sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed_runtime(db_path: Path) -> dict[str, object]:
    if db_path.exists():
        db_path.unlink()
    database = Database(RuntimeConfig(database_path=db_path, local_token="rc1-verification-token", writes_enabled=True))
    database.migrations.migrate()
    hashes: list[dict[str, object]] = []
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) VALUES (?,?,?,?,?,?,?,'runtime')",
            (PROJECT_ID, 7, "runtime-authority", 3, "story-runtime/v1", NOW, NOW),
        )
        for number, title, body, volume in CHAPTERS:
            commit_id = str(UUID(int=number))
            body_hash = sha256(body)
            artifact_hash = sha256(f"artifact-{number}")
            conn.execute(
                "INSERT INTO chapter_commits(commit_id,project_id,chapter_number,request_id,idempotency_key,request_hash,expected_revision,resulting_revision,state,body_sha256,artifact_sha256,schema_version,created_at,updated_at,finalized_at,error_details_json) VALUES (?,?,?,?,?,?,?,?, 'FINALIZED',?,?,?,?,?,?, '{}')",
                (commit_id, PROJECT_ID, number, f"request-{number}", f"key-{number}", sha256(f"request-{number}"), number + 3, number + 4, body_hash, artifact_hash, "story-runtime/v1", NOW, NOW, NOW),
            )
            conn.execute(
                "INSERT INTO chapter_artifacts(commit_id,project_id,chapter_number,title,body_text,summary,outline_fulfillment_json,review_json,state_mutation_proposal_json,evidence_spans_json,events_json,schema_version,body_sha256,checksum,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (commit_id, PROJECT_ID, number, title, body, f"运行时摘要{number}", json.dumps({"volume_id": volume}), "{}", "{}", "[]", "[]", "story-runtime/v1", body_hash, artifact_hash, NOW),
            )
            hashes.append({"number": number, "title": title, "body_sha256": body_hash, "characters": len(body)})
    collection_hash = sha256("\n".join(f"{row['number']}:{row['body_sha256']}" for row in hashes))
    return {"project_id": PROJECT_ID, "revision": 7, "latest": 3, "chapter_count": 3, "chapters": hashes, "collection_sha256": collection_hash}


def seed_project(project_root: Path, runtime_port: int, studio_port: int) -> None:
    if project_root.exists():
        shutil.rmtree(project_root)
    book_dir = project_root / "books" / PROJECT_ID
    (book_dir / "chapters").mkdir(parents=True)
    write_json(project_root / "inkos.json", {
        "name": "RC-1 Verification",
        "version": "0.1.0",
        "language": "zh",
        "llm": {"provider": "openai", "baseUrl": "http://127.0.0.1:9/v1", "apiKey": "", "model": "verification-no-llm"},
        "notify": [],
        "storyRuntime": {
            "mode": "story-runtime",
            "baseUrl": f"http://127.0.0.1:{runtime_port}",
            "apiTokenEnv": "RC1_VERIFICATION_TOKEN",
            "timeoutMs": 500,
            "maxContextTokens": 16000,
            "maxItems": 100,
            "fallbackOnUnavailable": False,
        },
    })
    write_json(book_dir / "book.json", {
        "id": PROJECT_ID,
        "title": "RC-1 统一事实源验收",
        "platform": "other",
        "genre": "sci-fi",
        "status": "active",
        "targetChapters": 10,
        "chapterWordCount": 2000,
        "authorityMode": "runtime",
        "createdAt": NOW,
        "updatedAt": NOW,
    })
    write_json(project_root / "verification.json", {"runtime_port": runtime_port, "studio_port": studio_port})


def local_meta(number: int, latest_override: int | None = None) -> dict[str, object]:
    return {
        "number": latest_override or number,
        "title": f"本地伪章节 {latest_override or number}",
        "status": "approved",
        "wordCount": 999,
        "createdAt": NOW,
        "updatedAt": NOW,
        "auditIssues": [],
        "lengthWarnings": [],
    }


def apply_state(project_root: Path, state: int) -> dict[str, object]:
    book_dir = project_root / "books" / PROJECT_ID
    chapters_dir = book_dir / "chapters"
    shutil.rmtree(chapters_dir, ignore_errors=True)
    chapters_dir.mkdir(parents=True)
    for name in ("analytics.json", "analytics-cache.json", "search-index.json", "export-cache.json"):
        (book_dir / name).unlink(missing_ok=True)

    if state == 1:
        index: list[dict[str, object]] | None = None
    elif state == 2:
        index = []
    elif state == 3:
        index = [local_meta(1), local_meta(2)]
    elif state == 4:
        index = [local_meta(number) for number in range(1, 5)]
        (chapters_dir / "0004_Local_Fake.md").write_text("# 本地伪第4章\n\n本地伪正文，绝不能出现。\n", encoding="utf-8")
    elif state == 5:
        index = [local_meta(number) for number in range(1, 4)]
        for number in range(1, 4):
            body = "# 本地冲突第2章\n\n本地冲突正文，绝不能出现。\n" if number == 2 else f"# 本地章节 {number}\n\n本地正文 {number}。\n"
            (chapters_dir / f"{number:04d}_Local.md").write_text(body, encoding="utf-8")
    elif state == 6:
        index = [local_meta(1, 99)]
        (chapters_dir / "0099_Local_Latest.md").write_text("# 本地 latest 99\n\n本地伪正文。\n", encoding="utf-8")
    else:
        raise ValueError(f"unknown local state: {state}")

    if index is not None:
        write_json(chapters_dir / "index.json", index)
    files = sorted(str(path.relative_to(book_dir)).replace("\\", "/") for path in book_dir.rglob("*") if path.is_file())
    result = {"state": state, "files": files, "index": index}
    write_json(project_root / "local-state.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed")
    seed.add_argument("--db", type=Path, required=True)
    seed.add_argument("--project-root", type=Path, required=True)
    seed.add_argument("--runtime-port", type=int, default=47931)
    seed.add_argument("--studio-port", type=int, default=45967)
    state = sub.add_parser("state")
    state.add_argument("--project-root", type=Path, required=True)
    state.add_argument("--number", type=int, required=True)
    args = parser.parse_args()
    if args.command == "seed":
        evidence = seed_runtime(args.db.resolve())
        seed_project(args.project_root.resolve(), args.runtime_port, args.studio_port)
        write_json(args.project_root.resolve() / "runtime-evidence.json", evidence)
        print(json.dumps(evidence, ensure_ascii=False))
    else:
        print(json.dumps(apply_state(args.project_root.resolve(), args.number), ensure_ascii=False))


if __name__ == "__main__":
    main()
