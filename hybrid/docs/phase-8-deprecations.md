# Phase 8 deprecations

- `storyRuntime.mode=legacy|shadow`: readable for old config, read-only for long-form; migrate immediately.
- `storyRuntime.fallbackOnUnavailable=true`: rejected for new configuration; migrated to false.
- direct Studio chapter/Truth/repair/resync/rewrite/review/import routes: HTTP 410 compatibility tombstones.
- CLI legacy book creation, file draft, file revision, state repair and Markdown resync: retired.
- automatic Markdown bootstrap and `state-bootstrap.ts`: removed. Explicit migration retains its own source parser and provenance contract.
- legacy Markdown chapter/Truth files: readable/exportable inputs and projections, never authority.

No deprecated item silently falls back to a writer.
