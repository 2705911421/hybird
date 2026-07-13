from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Scale:
    chapters: int
    chars_per_chapter: int
    characters: int
    relationships: int
    facts: int
    events: int
    threads: int


SCALES = {
    "smoke": Scale(12, 600, 20, 40, 200, 120, 12),
    "ci": Scale(80, 1000, 80, 400, 3000, 1200, 80),
    "million": Scale(600, 1800, 320, 3200, 24000, 12000, 420),
}

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
GIVEN = "安余陈月临舟岚星遥宁川禾清砚昭言墨白景澄夏冬秋"
PLACES = ("临江站", "北塔", "旧港", "云岭", "南环城", "镜湖", "长街", "地下档案馆")
OBJECTS = ("铜钥匙", "蓝色日志", "折叠地图", "旧车票", "信标", "校准器", "密封信")


def _chapter_body(rng: random.Random, chapter: int, target: int) -> str:
    sentences = []
    while len("".join(sentences)) < target:
        place = rng.choice(PLACES)
        obj = rng.choice(OBJECTS)
        minute = rng.randrange(0, 60)
        sentences.append(
            f"第{chapter}章记录：{place}的钟在{minute:02d}分响起，值守员核对{obj}后，把坐标写入第{chapter % 9 + 1}条时间线。"
            f"雨声覆盖了脚步，但校验编号{chapter:04d}-{rng.randrange(1000):03d}仍清晰可辨。"
        )
    body = "".join(sentences)[:target]
    if chapter % 37 == 0:
        body += " 灯已恢复。🧭📚"
    return body


def build_fixture(scale: Scale, seed: int = 20260713) -> tuple[dict[str, Any], dict[str, Any], list[tuple[int, str]]]:
    rng = random.Random(seed)
    project_id = f"synthetic-{scale.chapters}-{seed}"
    chapters = [(chapter, _chapter_body(rng, chapter, scale.chars_per_chapter * (10 if chapter == scale.chapters else 1))) for chapter in range(1, scale.chapters + 1)]
    entities = []
    for index in range(scale.characters):
        name = SURNAMES[index % len(SURNAMES)] + GIVEN[(index * 3) % len(GIVEN)] + GIVEN[(index * 7 + 1) % len(GIVEN)]
        entities.append({
            "entity_id": f"char-{index:04d}", "entity_type": "character", "canonical_name": name,
            "aliases": [f"代号{index:04d}"],
            "attributes": {"location": PLACES[index % len(PLACES)], "timeline": index % 7, "status": "active"},
            "history": [{"revision": index % max(1, scale.chapters), "change": "deterministic fixture state"}],
        })
    relationships = [{
        "relationship_id": f"rel-{index:06d}",
        "source_entity_id": f"char-{index % scale.characters:04d}",
        "target_entity_id": f"char-{(index * 17 + 3) % scale.characters:04d}",
        "relationship_type": ("colleague", "relative", "rival", "witness")[index % 4],
        "attributes": {"strength": index % 11, "since_chapter": index % scale.chapters + 1},
    } for index in range(scale.relationships)]
    events = [{
        "event_id": f"evt-{index:07d}", "event_type": f"timeline.{index % 13}",
        "subject": f"char-{index % scale.characters:04d}", "chapter_number": index % scale.chapters + 1,
        "payload": {"timeline": index % 7, "place": PLACES[index % len(PLACES)], "ordinal": index},
        "evidence": [{"chapter": index % scale.chapters + 1, "fixture": True}], "confidence": 1.0,
    } for index in range(scale.events)]
    timeline = [{
        "timeline_id": f"time-{index:07d}", "sequence_key": f"{index % 7:02d}.{index:08d}",
        "title": f"时间线{index % 7}事件{index}", "event_id": f"evt-{index:07d}",
        "details": {"branch": index % 7, "chapter": index % scale.chapters + 1},
    } for index in range(min(scale.events, scale.chapters * 4))]
    threads = [{
        "thread_id": f"thread-{index:05d}", "title": f"伏笔{index:05d}：{OBJECTS[index % len(OBJECTS)]}",
        "status": "open" if index % 3 else "resolved", "introduced_chapter": index % scale.chapters + 1,
        "resolved_chapter": None if index % 3 else min(scale.chapters, index % scale.chapters + 9),
        "details": {"payoff_target": min(scale.chapters, index % scale.chapters + 30)},
    } for index in range(scale.threads)]
    facts = [{
        "fact_id": f"fact-{index:07d}", "subject": f"char-{index % scale.characters:04d}",
        "predicate": ("character.location", "character.status", "inventory.object", "timeline.branch", "relationship.note")[index % 5],
        "value": {"value": PLACES[(index % scale.characters) % len(PLACES)], "fixture": "常规"},
        "valid_from_revision": index % max(1, scale.chapters),
    } for index in range(scale.facts)]
    facts.extend([
        {"fact_id": "conflict-location-a", "subject": "char-0000", "predicate": "character.location", "value": "北塔", "valid_from_revision": 1},
        {"fact_id": "conflict-location-b", "subject": "char-0000", "predicate": "character.location", "value": "旧港", "valid_from_revision": 1},
    ])
    summaries = [{
        "chapter_number": chapter, "title": f"第{chapter:04d}章", "summary": f"时间线{chapter % 7}在{PLACES[chapter % len(PLACES)]}推进，并复核{OBJECTS[chapter % len(OBJECTS)]}。",
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    } for chapter, body in chapters]
    documents = [{
        "source_id": f"卷{(chapter - 1) // 100 + 1:02d}-章节-{chapter:04d}", "source_type": "chapter_body",
        "chapter_number": chapter, "text": body,
    } for chapter, body in chapters]
    fixture = {
        "project": {"project_id": project_id, "revision": scale.chapters, "phase": "drafting", "latest_chapter": scale.chapters, "authority_mode": "runtime"},
        "entities": entities, "relationships": relationships, "events": events, "timeline": timeline,
        "narrative_threads": threads, "chapter_summaries": summaries, "facts": facts, "retrieval_documents": documents,
    }
    manifest = {
        "format": "hybrid-synthetic-corpus/v1", "seed": seed, "scale": asdict(scale), "project_id": project_id,
        "chinese_characters": sum(len(body) for _, body in chapters), "chapters": len(chapters),
        "entities": len(entities), "relationships": len(relationships), "facts": len(facts),
        "events": len(events), "timelines": 7, "threads": len(threads),
        "features": ["conflicting-facts", "long-chapter", "emoji", "CJK-filenames", "multi-volume"],
        "copyright": "Generated from deterministic templates; contains no copied novel text.",
    }
    return fixture, manifest, chapters


def write_corpus(output: Path, fixture: dict[str, Any], manifest: dict[str, Any], chapters: list[tuple[int, str]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for chapter, body in chapters:
        volume = output / f"第{(chapter - 1) // 100 + 1:02d}卷"
        volume.mkdir(exist_ok=True)
        (volume / f"第{chapter:04d}章-合成语料.md").write_text(f"# 第{chapter:04d}章\n\n{body}\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "runtime-fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic, copyright-free Chinese long-form fixtures")
    parser.add_argument("--scale", choices=SCALES, default="million")
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture, manifest, chapters = build_fixture(SCALES[args.scale], args.seed)
    write_corpus(args.output, fixture, manifest, chapters)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
