# Writer Revision Binding

## Bound workflow

1. PipelineRunner verifies Runtime authority and reads Runtime project status.
2. It records project revision `R` and calculates the next chapter from Runtime
   `latest_chapter`.
3. `ProjectWriterNarrativeContextResolver` loads the recent chapter window with
   `ChapterExportPort.exportSnapshot(expectedRevision=R)`.
4. Composer sends `expected_revision=R` on its Runtime context query. Runtime
   rejects a stale request and rechecks the project revision after assembling
   context.
5. Writer receives the typed narrative DTO with `projectRevision=R`.
6. Prepare, review validation, revision validation, and commit continue to use
   `expected_revision=R`.

## Conflict semantics

If Runtime changes before either context operation, the operation returns a
revision conflict. If it changes after context assembly, commit returns its
existing revision conflict. There is no local reread, no context refresh that
mixes revisions, and no fallback draft persistence.

## Contract change

`QueryContextRequest` now accepts nullable `expected_revision`. Writer flows
always provide it. The Pydantic contract, JSON Schema, TypeScript client input,
and Runtime contract/unit tests are synchronized. Existing generic context
queries may omit it; they are not Writer revision-bound flows.
