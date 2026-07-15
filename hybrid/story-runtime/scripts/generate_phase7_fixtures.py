from __future__ import annotations

import argparse
import json
import os
import sqlite3
import zipfile
from pathlib import Path


def write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def inkos(root: Path, chapters: list[int], *, title: str = "Fixture") -> None:
    write(root / "inkos.json", json.dumps({"version": "1.7.0", "name": title}, ensure_ascii=False))
    write(root / "story" / "state" / "characters.json", json.dumps([{"id": "a", "name": "林澈", "aliases": ["阿澈"]}], ensure_ascii=False))
    for number in chapters:
        write(root / "chapters" / f"Ch{number:04d}.md", f"# 第{number}章\n\n章节 {number} 正文🙂")


def build(root: Path) -> dict[str, str]:
    catalog: dict[str, str] = {}
    inkos(root / "inkos-small", [1, 2]); catalog["inkos-small"] = "normal InkOS"
    inkos(root / "inkos-large", list(range(1, 501))); catalog["inkos-large"] = "500 chapter InkOS"
    inkos(root / "inkos-truth-conflict", [1]); write(root / "inkos-truth-conflict" / "story" / "current_state.md", "JSON 与 Markdown 不一致")
    catalog["inkos-truth-conflict"] = "Markdown JSON conflict"
    inkos(root / "chapter-gap", [1, 3]); catalog["chapter-gap"] = "chapter gap"
    inkos(root / "CJK-文件名-📚", [1]); catalog["CJK-文件名-📚"] = "CJK and emoji"
    write(root / "corrupt-json" / "inkos.json", "{"); catalog["corrupt-json"] = "corrupt JSON"
    write(root / "corrupt-sqlite" / "index.db", b"not sqlite"); write(root / "corrupt-sqlite" / ".webnovel" / "state.json", "{}")
    catalog["corrupt-sqlite"] = "corrupt SQLite"
    inkos(root / "alias-collision", [1]); write(root / "alias-collision" / "story" / "state" / "characters.json", json.dumps([{"name": "甲", "aliases": ["小林"]}, {"name": "乙", "aliases": ["小林"]}], ensure_ascii=False))
    catalog["alias-collision"] = "alias collision"
    inkos(root / "multi-volume", [1, 2]); write(root / "multi-volume" / "volumes" / "volume-1.json", '{"chapters":[1]}'); write(root / "multi-volume" / "volumes" / "volume-2.json", '{"chapters":[2]}')
    catalog["multi-volume"] = "multi-volume"
    # Keep every component below Linux's 255-byte NAME_MAX while preserving a
    # genuinely long, CJK-heavy path for Windows migration coverage.
    long_root = root / "windows-long-path"
    for _ in range(30):
        long_root /= "长目录"
    inkos(long_root, [1]); catalog["windows-long-path"] = "Windows long path"
    web = root / "webnovel-mismatch"; write(web / ".webnovel" / "state.json", '{"version":"6.2"}'); write(web / "events" / "events.json", '[{"event_id":"e1","event_type":"fact.set","subject":"p"}]')
    db = sqlite3.connect(web / "index.db")
    try:
        db.execute("CREATE TABLE events(event_id TEXT)"); db.executemany("INSERT INTO events VALUES (?)", [("e1",), ("e2",)]); db.commit()
    finally: db.close()
    catalog["webnovel-mismatch"] = "webnovel JSON SQLite mismatch"
    archive_root = root / "zip-slip"; write(archive_root / "inkos.json", '{"version":"1.7.0"}')
    with zipfile.ZipFile(archive_root / "unsafe.zip", "w") as archive: archive.writestr("../escape.json", "{}")
    catalog["zip-slip"] = "archive path traversal"
    million = root / "million-char-synthetic"; write(million / "inkos.json", '{"version":"1.7.0"}')
    block = "潮声穿过灯塔，林澈记住这一刻。" * 313
    for number in range(1, 101): write(million / "chapters" / f"Ch{number:04d}.md", f"# 第{number}章\n\n{block}")
    catalog["million-char-synthetic"] = "at least one million UTF-8 fiction characters"
    if hasattr(os, "symlink"):
        attack = root / "symlink-attack"; inkos(attack, [1]); outside = root / "outside.json"; write(outside, '{"outside":true}')
        try: os.symlink(outside, attack / "story" / "state" / "escape.json")
        except OSError: pass
        catalog["symlink-attack"] = "symlink escape"
    write(root / "fixture-catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2))
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    build(args.output)


if __name__ == "__main__":
    main()
