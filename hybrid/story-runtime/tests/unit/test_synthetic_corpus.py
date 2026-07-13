from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_synthetic_corpus import SCALES, build_fixture  # noqa: E402


def test_million_scale_is_deterministic_and_meets_capacity_shape():
    first, manifest, chapters = build_fixture(SCALES["million"], 20260713)
    second, second_manifest, _ = build_fixture(SCALES["million"], 20260713)
    assert manifest == second_manifest
    assert first["facts"][:10] == second["facts"][:10]
    assert manifest["chinese_characters"] >= 1_000_000
    assert 500 <= manifest["chapters"] <= 1000
    assert manifest["entities"] >= 300
    assert manifest["relationships"] >= 3000
    assert manifest["facts"] >= 20_000
    assert manifest["events"] >= 10_000
    assert manifest["threads"] >= 400
    assert any("🧭" in body for _, body in chapters)
    assert any(fact["fact_id"].startswith("conflict-") for fact in first["facts"])
