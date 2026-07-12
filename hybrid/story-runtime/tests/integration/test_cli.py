import json

from story_runtime.cli import main


def test_cli_initializes_and_reads_fixture(tmp_path, capsys):
    from pathlib import Path
    fixture = Path(__file__).resolve().parents[2] / "fixtures/lighthouse-project.json"
    db = tmp_path / "cli.db"
    assert main(["--db", str(db), "init-fixture", "--fixture", str(fixture)]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["status"] == "initialized"
    assert main(["--db", str(db), "status", "lighthouse-fixture"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["latest_chapter"] == 3
    assert main(["--db", str(db), "doctor", "lighthouse-fixture", "--deep"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["status"] == "ok"
