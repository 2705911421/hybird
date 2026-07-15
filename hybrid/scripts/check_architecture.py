from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INKOS = ROOT / "inkos" / "packages"
RUNTIME = ROOT / "hybrid" / "story-runtime" / "src" / "story_runtime"
failures: list[str] = []


def fail(rule: str, path: Path, detail: str) -> None:
    failures.append(f"{rule}: {path.relative_to(ROOT)}: {detail}")


def files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in {"node_modules", "dist", ".git", "coverage"}]
        found.extend(Path(current) / name for name in names if Path(name).suffix in suffixes)
    return found


ts_files = files(INKOS, (".ts", ".tsx"))
product_ts = [p for p in ts_files if "__tests__" not in p.parts]

# G1: TypeScript never imports Python implementation internals.
for path in product_ts:
    text = path.read_text(encoding="utf-8")
    for spec in re.findall(r"(?:from\s+|import\s*\()\s*['\"]([^'\"]+)", text):
        if spec.endswith(".py") or "story-runtime/src" in spec or "story_runtime" in spec:
            fail("G1_TS_PYTHON_INTERNAL_IMPORT", path, spec)

# G2/G3: InkOS and Studio cannot open Runtime SQLite or Runtime data directories.
runtime_storage_tokens = ("STORY_RUNTIME_DB", "story-runtime/data", "story.db", "runtime.sqlite")
for path in product_ts:
    text = path.read_text(encoding="utf-8")
    for token in runtime_storage_tokens:
        if token in text and not (path.name == "agent-tools.ts" and "AUTHORITY_PATH_FORBIDDEN" in text):
            fail("G2_NO_RUNTIME_STORAGE_ACCESS", path, token)
for path in files(INKOS / "studio" / "src", (".ts", ".tsx")):
    text = path.read_text(encoding="utf-8")
    if re.search(r"node:sqlite|better-sqlite3|sqlite3|DatabaseSync", text):
        fail("G3_STUDIO_NO_SQLITE", path, "SQLite API")

# G4: the long-form Agent registry contains no authority mutator or generic file mutator.
session = INKOS / "core" / "src" / "agent" / "agent-session.ts"
session_text = session.read_text(encoding="utf-8")
for name in ("createWriteTruthFileTool", "createPatchChapterTextTool", "createReplaceChapterTextTool",
             "createRenameEntityTool", "createImportChaptersTool", "createEditTool", "createWriteFileTool"):
    if name in session_text:
        fail("G4_AGENT_NO_AUTHORITY_WRITER", session, name)
agent_tools_path = INKOS / "core" / "src" / "agent" / "agent-tools.ts"
agent_tools_text = agent_tools_path.read_text(encoding="utf-8")
for name in ("createWriteTruthFileTool", "createPatchChapterTextTool", "createReplaceChapterTextTool",
             "createRenameEntityTool", "createImportChaptersTool", "createEditTool", "createWriteFileTool"):
    if name in agent_tools_text:
        fail("G4_AGENT_MUTATOR_REMOVED", agent_tools_path, name)
agent_prompt = INKOS / "core" / "src" / "agent" / "agent-system-prompt.ts"
prompt_text = agent_prompt.read_text(encoding="utf-8")
for name in ("write_truth_file", "rename_entity", "patch_chapter_text", "replace_chapter_text", "import_chapters"):
    if name in prompt_text:
        fail("G4_AGENT_PROMPT_NO_REMOVED_CAPABILITY", agent_prompt, name)
for token in ("AUTHORITY_PATH_FORBIDDEN", "migration snapshot", "Runtime databases"):
    if token not in agent_tools_text:
        fail("G4_AGENT_READ_BOUNDARY", agent_tools_path, token)

# G5/G7: normal long-form pipeline has no legacy writer, MemoryDB writer, or Markdown bootstrap.
pipeline_root = INKOS / "core" / "src" / "pipeline"
for path in files(pipeline_root, (".ts",)):
    text = path.read_text(encoding="utf-8")
    for token in ("LegacyChapterPersistence", "persistChapterArtifacts", "saveNewTruthFiles",
                  "bootstrapStructuredStateFromMarkdown", "rewriteStructuredStateFromMarkdown", "new MemoryDB"):
        if token in text:
            fail("G5_SINGLE_LONGFORM_PIPELINE", path, token)
interaction_tools = INKOS / "core" / "src" / "interaction" / "project-tools.ts"
interaction_text = interaction_tools.read_text(encoding="utf-8")
for token in ("executeEditTransaction", "assertSafeTruthFileName", "withBookMutationLock"):
    if token in interaction_text:
        fail("G5_NO_INTERACTION_TRUTH_WRITER", interaction_tools, token)
for path in product_ts:
    if "bootstrapStructuredStateFromMarkdown" in path.read_text(encoding="utf-8"):
        fail("G7_NO_RUNTIME_MARKDOWN_BOOTSTRAP", path, "bootstrapStructuredStateFromMarkdown")

# Non-long-form SQLite is isolated: only Interactive Film may instantiate MemoryDB.
for path in product_ts:
    if "new MemoryDB" in path.read_text(encoding="utf-8") and path.name != "film-authoring-tools.ts":
        fail("G2_MEMORYDB_NON_LONGFORM_ONLY", path, "new MemoryDB")

# G6: Runtime is deterministic and has no LLM SDK/import.
for path in files(RUNTIME, (".py",)):
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = [n for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for n in ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""])]
    for name in imports:
        if name.split(".")[0] in {"openai", "anthropic", "langchain", "litellm", "transformers"}:
            fail("G6_RUNTIME_NO_LLM", path, name)

# G8: every authority mutation contract carries the five common write metadata fields.
contracts = ast.parse((RUNTIME / "contracts.py").read_text(encoding="utf-8"))
common_fields = {"request_id", "idempotency_key", "project_id", "schema_version", "expected_revision"}
write_contracts = {"PrepareChapterRequest", "ValidateChapterArtifactsRequest", "CommitChapterRequest",
                   "AppendEventsRequest", "TypedDiffCommandRequest", "ReplayProjectionsRequest",
                   "ValidateReviewsRequest", "StoreReviewDecisionRequest", "ValidateRevisionRequest"}
classes = {node.name: node for node in contracts.body if isinstance(node, ast.ClassDef)}
base = classes["CommonWriteContext"]
declared = {node.target.id for node in base.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
if declared != common_fields:
    fail("G8_WRITE_METADATA", RUNTIME / "contracts.py", f"CommonWriteContext={sorted(declared)}")
for name in write_contracts:
    node = classes.get(name)
    if node is None or not any(isinstance(base_node, ast.Name) and base_node.id == "CommonWriteContext" for base_node in node.bases):
        fail("G8_WRITE_METADATA", RUNTIME / "contracts.py", f"{name} must inherit CommonWriteContext")

# G9/G10: migration provenance remains explicit; search indexes are never authority.
migration = (RUNTIME / "migration_jobs.py").read_text(encoding="utf-8")
for token in ("source_path_fingerprint", "source_checksum_manifest", "mapping_version", "provenance"):
    if token not in migration:
        fail("G9_MIGRATION_PROVENANCE", RUNTIME / "migration_jobs.py", token)
for path in files(RUNTIME, (".py",)):
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"(?:vector|fts).{0,40}(?:authority|authoritative)|(?:authority|authoritative).{0,40}(?:vector|fts)", line, re.I):
            if "not authority" not in line.lower() and "non-author" not in line.lower() and "authoritative_data_changed\": False" not in line:
                fail("G10_INDEX_NOT_AUTHORITY", path, f"line {line_no}")

# The upstream webnovel/Claude package is provenance-only and cannot enter product imports or manifests.
for path in product_ts:
    text = path.read_text(encoding="utf-8")
    imports = re.findall(r"(?:from\s+|import\s*\()\s*['\"]([^'\"]+)", text)
    if any("webnovel-writer" in spec or ".claude-plugin" in spec for spec in imports):
        fail("G11_NO_DUPLICATE_DASHBOARD_OR_HOOK", path, "upstream runtime import")
manifest = (ROOT / "inkos" / "package.json").read_text(encoding="utf-8")
if re.search(r'"(?:webnovel-writer|claude-plugin)"\s*:', manifest):
    fail("G11_NO_DUPLICATE_DASHBOARD_OR_HOOK", ROOT / "inkos" / "package.json", "upstream dependency")

# RC-2B1: revision membership and allocation have one deep Runtime module.
allocator_path = RUNTIME / "revision_manifests.py"
allocator_text = allocator_path.read_text(encoding="utf-8")
chapter_text = (RUNTIME / "chapter_commits.py").read_text(encoding="utf-8")
migrations_text = (RUNTIME / "migrations.py").read_text(encoding="utf-8")
migration_jobs_text = (RUNTIME / "migration_jobs.py").read_text(encoding="utf-8")
api_text = (RUNTIME / "api.py").read_text(encoding="utf-8")

if "class ProjectRevisionAllocator" not in allocator_text or "class RevisionManifestRepository" not in allocator_text:
    fail("G12_SINGLE_REVISION_ALLOCATOR", allocator_path, "allocator/repository interface missing")
for path in files(RUNTIME, (".py",)):
    text = path.read_text(encoding="utf-8")
    if path.name not in {"revision_manifests.py", "migration_jobs.py"} and re.search(r"UPDATE\s+projects\s+SET\s+revision", text, re.I):
        fail("G12_SINGLE_REVISION_ALLOCATOR", path, "direct project revision update")
    if path.name != "revision_manifests.py" and re.search(r"expected_revision\s*\+\s*1|revision\s*\+=\s*1", text):
        fail("G12_SINGLE_REVISION_ALLOCATOR", path, "independent revision arithmetic")
if chapter_text.count("self.revision_allocator.execute(") != 2:
    fail("G13_AUTHORITY_WRITES_USE_ALLOCATOR", RUNTIME / "chapter_commits.py", "chapter and command seams must both allocate")
for name in ("reviews.py", "outbox.py", "operations.py", "observability.py", "services.py"):
    if "ProjectRevisionAllocator" in (RUNTIME / name).read_text(encoding="utf-8"):
        fail("G14_NEUTRAL_OPERATIONS_NO_ALLOCATOR", RUNTIME / name, "revision-neutral module imports allocator")
if "ProjectRevisionAllocator" in chapter_text[chapter_text.index("    def replay("):chapter_text.index("    def append_operator_events(")]:
    fail("G14_NEUTRAL_OPERATIONS_NO_ALLOCATOR", RUNTIME / "chapter_commits.py", "replay calls allocator")
for token in ("project_revisions_immutable_update", "project_revisions_immutable_delete", "RAISE(ABORT, 'project revision manifests are immutable')"):
    if token not in migrations_text:
        fail("G15_MANIFEST_IMMUTABLE", RUNTIME / "migrations.py", token)
manifest_schema = migrations_text[migrations_text.index("CREATE TABLE project_revisions"):migrations_text.index("CREATE UNIQUE INDEX project_revisions_commit_idx")]
for token in ("body_text", "payload_json", "state_mutation_proposal_json"):
    if token in manifest_schema:
        fail("G16_MANIFEST_NOT_STATE_OR_PAYLOAD", RUNTIME / "migrations.py", token)
if "revision += 1" in migration_jobs_text or "applied_revision,aggregate_type" not in migration_jobs_text or "SCHEMA_VERSION, now, None" not in migration_jobs_text:
    fail("G17_MIGRATION_NO_FAKE_INTERMEDIATE_HISTORY", RUNTIME / "migration_jobs.py", "legacy rows must not allocate revisions")
if "HISTORY_NOT_IMPLEMENTED" not in api_text:
    fail("G18_NO_PSEUDO_HISTORICAL_API", RUNTIME / "api.py", "at_revision must fail closed in Batch 1")
if "def append_operator_events" not in chapter_text or "self.revision_allocator.execute(" not in chapter_text[chapter_text.index("    def append_operator_events("):chapter_text.index("    def apply_typed_diff(")]:
    fail("G19_OPERATOR_APPEND_USES_ALLOCATOR", RUNTIME / "chapter_commits.py", "operator append bypasses allocator")
if "ordered_event_ids" not in allocator_text or "artifact_references" not in allocator_text or "canonical_manifest_hash" not in allocator_text:
    fail("G20_MANIFEST_OWNERSHIP_INDEX_ONLY", allocator_path, "membership/hash index fields missing")

if failures:
    print("Phase 8 architecture gates FAILED")
    for item in failures:
        print(f"- {item}")
    raise SystemExit(1)
print("Architecture gates passed (RC-1 authority rules + RC-2B1 revision-manifest rules).")
