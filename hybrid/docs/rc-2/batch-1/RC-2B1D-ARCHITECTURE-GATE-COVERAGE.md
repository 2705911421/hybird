# RC-2B1D Architecture Gate Coverage

## Scan closure

`hybrid/scripts/check_architecture.py` walks the complete Runtime production root `hybrid/story-runtime/src/story_runtime/**/*.py`. A test can substitute an external copy through `HYBRID_ARCH_RUNTIME_ROOT`; the production invocation uses the repository root. New production Python files are scanned without editing a file list.

Central directory exclusions are limited to generated/non-production trees: `tests`, `fixtures`, `generated`, `vendor`, `__pycache__`, `node_modules`, `dist`, `.git`, and `coverage`. Migration SQL/DDL constants at module scope in `migrations.py` are data and excluded; executable functions in that file remain scanned.

## Detected mutation primitives

The AST/string scanner detects and reports file, line, symbol, call path and primitive for:

- direct `UPDATE projects ... SET ... revision =` SQL, including aliases, case and whitespace/newline variants;
- `revision += 1`;
- `revision = revision + 1`;
- direct attribute assignment such as `project.revision = ...`;
- helper/repository wrappers because the defining production symbol is itself in the scan closure.

Failure output has the form:

```text
production-root -> <file>:<symbol> -> <mutation primitive>
```

## Exact exceptions

No file or directory receives a revision-mutation exemption. The only exact `(path, symbol, primitive)` allowances are:

| Path | Symbol | Reason / authority |
| --- | --- | --- |
| `revision_manifests.py` | `ProjectRevisionAllocator.execute` | approved native CAS allocator, ADR-RC2-001 |
| `revision_manifests.py` | `ProjectRevisionAllocator._ensure_lineage` | honest bootstrap-boundary establishment, ADR-RC2-007 |
| `migration_jobs.py` | `LegacyMigrationService._import_cir` | current-state-only legacy import boundary, ADR-RC2-007 |
| `migration_jobs.py` | `LegacyMigrationService._replay_cir_hash` | isolated temporary verification database, ADR-RC2-005/007 |

`migration_jobs.py` is no longer exempt as a file. Any additional function in it is scanned and fails on a revision mutation.

## Mutation-test evidence

`tests/contract/test_rc2b1d_architecture_gate.py` copies the production package to an external pytest temp directory and verifies:

1. direct SQL in `migration_jobs.py` fails;
2. a new unlisted production file with `revision += 1` fails;
3. a recovery job with attribute revision arithmetic fails;
4. a CLI command with case/newline-varied SQL fails;
5. a helper-wrapped aliased SQL string fails;
6. a repository method with revision SQL fails;
7. the pristine approved allocator/import symbols pass;
8. test fixture directories are excluded;
9. module-level migration DDL data is excluded while functions remain scanned.

The final suite passed 9/9. The TypeScript authority call-graph gate also remained green at 439 modules, 319 import edges and 24022 call sites.
