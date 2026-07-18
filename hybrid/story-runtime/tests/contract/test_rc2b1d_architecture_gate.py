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


def test_architecture_gate_traces_job_through_dynamic_repository_helper(tmp_path) -> None:
    runtime = _runtime_copy(tmp_path)
    repository = runtime / "repository.py"
    repository.write_text(
        repository.read_text(encoding="utf-8")
        + "\n\nclass IndirectBypassRepository:\n"
          "    def set_project_revision(self, conn, project_id, value):\n"
          "        field = 'revision'\n"
          "        sql = f'UPDATE projects SET {field}=? WHERE project_id=?'\n"
          "        conn.execute(sql, (value, project_id))\n",
        encoding="utf-8",
    )
    job = runtime / "indirect_migration_job.py"
    job.write_text(
        "def migrate(repository, conn, project_id, revision):\n"
        "    return repository.set_project_revision(conn, project_id, revision + 1)\n",
        encoding="utf-8",
    )

    result = _run_gate(runtime)
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "indirect_migration_job.py:migrate" in output
    assert "repository.py:IndirectBypassRepository.set_project_revision" in output
    assert "forbidden revision write sink" in output


@pytest.mark.parametrize(
    ("case", "additions"),
    [
        (
            "cli-service-repository",
            {
                "repository.py": "\n\nclass MatrixRepo:\n    def set_project_revision(self, conn, value):\n        field='revision'\n        conn.execute(f'UPDATE projects SET {field}=?', (value,))\n",
                "matrix_service.py": "class MatrixService:\n    def advance(self, repo, conn, value):\n        return repo.set_project_revision(conn, value)\n",
                "matrix_cli.py": "def command(service, repo, conn, value):\n    return service.advance(repo, conn, value)\n",
            },
        ),
        (
            "route-multihop-raw-sql",
            {
                "matrix_repository.py": "def write(conn, value):\n    column='revision'\n    conn.execute(f'UPDATE projects SET {column}=?', (value,))\n",
                "matrix_helper.py": "from matrix_repository import write\ndef helper(conn, value):\n    return write(conn, value)\n",
                "matrix_service.py": "from matrix_helper import helper\ndef service(conn, value):\n    return helper(conn, value)\n",
                "matrix_route.py": "from matrix_service import service\ndef route(conn, value):\n    return service(conn, value)\n",
            },
        ),
        (
            "migration-adapter-update-fields",
            {
                "matrix_adapter.py": "def adapt(repo, project_id, value):\n    return repo.update_fields(project_id, {'revision': value})\n",
                "matrix_migration_job.py": "from matrix_adapter import adapt\ndef migrate(repo, project_id, value):\n    return adapt(repo, project_id, value)\n",
            },
        ),
        (
            "generic-set-column",
            {"matrix_job.py": "def run(repo, value):\n    return repo.set_column('revision', value)\n"},
        ),
        (
            "dynamic-keyword-field",
            {"matrix_job.py": "def run(repo, value):\n    return repo.set_project_value(field='revision', value=value)\n"},
        ),
        (
            "generic-sql-executor",
            {"matrix_job.py": "def run(executor, value):\n    field='revision'\n    sql=f'UPDATE projects SET {field}=?'\n    return executor(sql, value)\n"},
        ),
        (
            "import-alias",
            {
                "matrix_repository.py": "def set_column(conn, value):\n    field='revision'\n    conn.execute(f'UPDATE projects SET {field}=?', (value,))\n",
                "matrix_job.py": "from matrix_repository import set_column as mutate\ndef run(conn, value):\n    return mutate(conn, value)\n",
            },
        ),
        (
            "helper-reexport",
            {
                "matrix_repository.py": "def set_column(conn, field, value):\n    conn.execute(f'UPDATE projects SET {field}=?', (value,))\n",
                "matrix_adapter.py": "from matrix_repository import set_column\n",
                "matrix_job.py": "from matrix_adapter import set_column\ndef run(conn, value):\n    return set_column(conn, 'revision', value)\n",
            },
        ),
        (
            "local-callable-alias",
            {
                "matrix_repository.py": "def set_column(conn, value):\n    field='revision'\n    conn.execute(f'UPDATE projects SET {field}=?', (value,))\n",
                "matrix_job.py": "import matrix_repository\ndef run(conn, value):\n    mutate=matrix_repository.set_column\n    return mutate(conn, value)\n",
            },
        ),
        (
            "parameterized-field-name",
            {"matrix_job.py": "def run(repo, field, value):\n    field='revision'\n    return repo.execute_update('projects', {field: value})\n"},
        ),
        (
            "orm-expression",
            {"matrix_job.py": "def run(project, value):\n    project.revision = value\n"},
        ),
    ],
)
def test_architecture_gate_blocks_indirect_mutation_matrix(
    tmp_path, case: str, additions: dict[str, str]
) -> None:
    runtime = _runtime_copy(tmp_path)
    for relative_path, source in additions.items():
        target = runtime / relative_path
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(existing + source, encoding="utf-8")

    result = _run_gate(runtime)
    output = result.stdout + result.stderr

    assert result.returncode == 1, f"{case} escaped\n{output}"
    assert "G12_SINGLE_REVISION_ALLOCATOR" in output
    assert "line " in output
    assert "forbidden revision write sink" in output


def test_architecture_gate_allows_revision_neutral_repository_helper(tmp_path) -> None:
    runtime = _runtime_copy(tmp_path)
    target = runtime / "neutral_maintenance_job.py"
    target.write_text(
        "def maintain(repo, project_id):\n"
        "    return repo.update_fields(project_id, {'phase': 'ready'})\n",
        encoding="utf-8",
    )

    result = _run_gate(runtime)

    assert result.returncode == 0, result.stdout + result.stderr
