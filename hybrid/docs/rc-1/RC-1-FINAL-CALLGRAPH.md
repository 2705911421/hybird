# RC-1 Final Callgraph

## Product read path

```text
Studio routes/components
CLI commands
TUI interactive commands
analytics / search / export
pipeline / agents
        |
        v
ChapterApplicationService / typed chapter ports
        |
        v
ProjectChapterAuthorityResolver
        |
        +-- authorityMode=runtime
        |      -> StoryRuntimeChapterReadAdapter
        |      -> StoryRuntimeClient.assertCompatible()
        |      -> Runtime collection/detail/aggregate/search/export/context
        |
        +-- authorityMode=legacy (explicit legacy project only)
               -> LegacyChapterReadAdapter
               -> local index/Markdown
```

Runtime adapter operations first perform health/version/schema compatibility. Runtime fault maps to typed application/UI/CLI/TUI error and terminates; there is no edge from the error node to Legacy adapter or filesystem readers.

## Writer path

```text
PipelineRunner
  -> Runtime status (revision N, latest chapter)
  -> ProjectWriterNarrativeContextResolver(authorityMode=runtime, expectedRevision=N)
  -> StoryRuntimeWriterNarrativeContextAdapter
  -> Runtime revision-bound chapter export/context
  -> WriterAgent.writeChapter(narrativeContext)
```

`WriterAgent` consumes injected Runtime narrative context. Architecture gate rejects chapter-directory filesystem imports or reachable local chapter readers in the Runtime Writer path. Runtime-mode system prompt additionally forbids file-tool bypass.

## UI/TUI fault path

```text
connection refused / timeout / degraded / malformed DTO /
version mismatch / authorization / DB locked
        -> StoryRuntimeClientError
        -> ChapterApplicationError
        -> Studio explicit unavailable UI | CLI non-zero | TUI error
        -> export blocked + write blocked
        -> retry same Runtime capability after recovery
```

Retry never switches authority. Local chapter 4, conflicting chapter 2, latest 99 and missing projection are outside the Runtime product result graph.

## Export path

```text
Studio / CLI / TUI export request
  -> ChapterExportPort.exportSnapshot(expected revision)
  -> Runtime single-revision snapshot
  -> formatter / downloadable artifact
```

Generated files have no reverse edge into current chapter reads. Runtime failure stops export rather than silently using a stale artifact.
