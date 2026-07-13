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
    assert main(["--db", str(db), "overview", "lighthouse-fixture"]) == 0
    overview = json.loads(capsys.readouterr().out)
    assert overview["current_revision"] == 7
    assert main(["--db", str(db), "events", "lighthouse-fixture", "--limit", "2"]) == 0
    events = json.loads(capsys.readouterr().out)
    assert len(events["items"]) == 2
    assert main(["--db", str(db), "projections", "lighthouse-fixture"]) == 0
    projections = json.loads(capsys.readouterr().out)
    assert projections["items"]
    assert main(["--db", str(db), "diagnostics", "lighthouse-fixture"]) == 0
    diagnostics = json.loads(capsys.readouterr().out)
    assert diagnostics["project_id"] == "lighthouse-fixture"
    assert main(["--db", str(db), "run-outbox", "--project-id", "lighthouse-fixture"]) == 0
    outbox = json.loads(capsys.readouterr().out)
    assert outbox == {
        "request_id": outbox["request_id"], "claimed": 0, "completed": 0,
        "failed": 0, "pending": 0,
    }
