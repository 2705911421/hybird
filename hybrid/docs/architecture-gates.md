# Architecture gates

Run from repository root:

```powershell
python hybrid/scripts/check_architecture.py
```

The same command runs in `.github/workflows/ci.yml`.

| Gate | Enforced rule |
|---|---|
| G1 | TypeScript cannot import Python internals. |
| G2 | InkOS cannot access Runtime SQLite/data; non-long-form `MemoryDB` construction is Film-only. |
| G3 | Studio cannot import a SQLite API. |
| G4 | Agent registry, implementation and long-form prompts contain no Truth/chapter/import/generic file mutator; read tooling denies Runtime data and migration snapshots. |
| G5 | Long-form pipeline and interaction tools contain no legacy persistence, Markdown rewrite or file edit transaction. |
| G6 | Runtime source imports no LLM SDK. |
| G7 | Markdown bootstrap module is absent and no normal-runtime path can auto-trigger an importer. |
| G8 | Authority write DTOs inherit the five common metadata fields. |
| G9 | Migration retains fingerprint, checksum manifest, mapping version and provenance. |
| G10 | FTS/vector indexes are not marked authority. |
| G11 | InkOS product imports/manifests cannot include the upstream webnovel Dashboard or Claude plugin runtime. |

The checks are textual/import-AST/schema inheritance gates designed to fail CI, not review conventions.
