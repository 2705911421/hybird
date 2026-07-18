from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


WORKSPACE = Path(__file__).resolve().parents[4]
RUNTIME_SOURCE = WORKSPACE / "hybrid" / "story-runtime" / "src" / "story_runtime"
GATE = WORKSPACE / "hybrid" / "scripts" / "check_architecture.py"


def _runtime_copy(tmp_path: Path) -> Path:
    target = tmp_path / "story_runtime"
    shutil.copytree(RUNTIME_SOURCE, target)
    return target


def _run_gate(runtime: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HYBRID_ARCH_RUNTIME_ROOT": str(runtime)}
    return subprocess.run(
        [sys.executable, str(GATE)],
        cwd=WORKSPACE,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def test_architecture_gate_scans_migration_jobs_for_allocator_bypass(tmp_path) -> None:
    runtime = _runtime_copy(tmp_path)
    target = runtime / "migration_jobs.py"
    target.write_text(
        target.read_text(encoding="utf-8")
        + "\n\ndef injected_bypass(conn, project_id):\n"
          "    conn.execute(\"UPDATE projects SET revision = revision + 1 WHERE project_id=?\", (project_id,))\n",
        encoding="utf-8",
    )

    result = _run_gate(runtime)
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "G12_SINGLE_REVISION_ALLOCATOR" in output
    assert "migration_jobs.py" in output
    assert "injected_bypass" in output
    assert "direct project revision SQL" in output


@pytest.mark.parametrize(
    ("relative_path", "source", "symbol", "primitive"),
    [
        (
            "unlisted_authority_job.py",
            "def mutate(project):\n    project.revision += 1\n",
            "mutate",
            "independent revision arithmetic",
        ),
        (
            "recovery_jobs.py",
            "def recover(project):\n    project.revision = project.revision + 1\n",
            "recover",
            "independent revision arithmetic",
        ),
        (
            "cli.py",
            "\n\ndef unsafe_cli(conn):\n"
            "    conn.execute(\"update PROJECTS\\n set REVISION = REVISION + 1 where project_id = ?\")\n",
            "unsafe_cli",
            "direct project revision SQL",
        ),
        (
            "migration_jobs.py",
            "\n\ndef helper_wrapped_bypass(conn):\n"
            "    sql = \"UpDaTe projects AS p\\n  SeT revision=revision+1 WHERE p.project_id=?\"\n"
            "    conn.execute(sql)\n",
            "helper_wrapped_bypass",
            "direct project revision SQL",
        ),
        (
            "repository.py",
            "\n\nclass UnsafeRevisionRepository:\n"
            "    def advance(self, conn):\n"
            "        conn.execute(\"UPDATE projects SET phase='x', revision = revision + 1 WHERE project_id=?\")\n",
            "UnsafeRevisionRepository.advance",
            "direct project revision SQL",
        ),
    ],
)
def test_architecture_gate_rejects_production_bypass_variants(
    tmp_path, relative_path: str, source: str, symbol: str, primitive: str
) -> None:
    runtime = _runtime_copy(tmp_path)
    target = runtime / relative_path
    if target.exists():
        source = target.read_text(encoding="utf-8") + source
    target.write_text(source, encoding="utf-8")

    result = _run_gate(runtime)
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert relative_path in output
    assert symbol in output
    assert primitive in output


def test_architecture_gate_allows_only_exact_allocator_and_legacy_boundary_symbols(tmp_path) -> None:
    result = _run_gate(_runtime_copy(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_gate_excludes_test_fixtures_but_not_new_production_files(tmp_path) -> None:
    runtime = _runtime_copy(tmp_path)
    fixture = runtime / "tests" / "fixtures" / "legacy.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        "def fixture(project):\n    project.revision += 1\n",
        encoding="utf-8",
    )

    result = _run_gate(runtime)

    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_gate_excludes_migration_ddl_data_only(tmp_path) -> None:
    runtime = _runtime_copy(tmp_path)
    target = runtime / "migrations.py"
    target.write_text(
        target.read_text(encoding="utf-8")
        + "\nRC2B1D_DDL_FIXTURE = \"CREATE TRIGGER fixture AFTER INSERT ON x "
          "BEGIN UPDATE projects SET revision = revision + 1; END\"\n",
        encoding="utf-8",
    )

    result = _run_gate(runtime)

    assert result.returncode == 0, result.stdout + result.stderr
