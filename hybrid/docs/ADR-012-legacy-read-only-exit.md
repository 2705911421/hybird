# ADR-012: legacy long-form read-only exit

Status: accepted  
Date: 2026-07-13

Unmigrated legacy projects may be opened for reading, export, migration dry-run and backup. Legacy writing, chapter replacement, Truth mutation, Markdown resync and state repair are disabled by code and return `LEGACY_LONG_FORM_READ_ONLY` or HTTP 410 guidance.

`legacy` and `shadow` configuration values remain parseable only so old projects can open safely. They do not select a writer or context fallback. The Phase 8 config migrator creates `inkos.json.pre-phase8.bak`, emits every changed key, sets Runtime mode, disables fallback and removes obsolete authority/dashboard/plugin/mirror keys.

There is no transitional dual-write release. Rollback uses the previous application/Runtime packages and a verified pre-migration snapshot, never a re-enabled mirror.
