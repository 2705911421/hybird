# Runtime Writer Context Boundary

## Ownership rule

For a Runtime-authority project, the Writer receives one typed
`WriterNarrativeContext` and does not select or read a chapter source. The DTO
contains ordered recent chapters, title, summary, full body, body checksum,
finalized revision, latest chapter, prior ending, source, and project revision.

## Seam

`WriterNarrativeContextPort` has two adapters:

- `StoryRuntimeWriterNarrativeContextAdapter` uses the existing
  `ChapterExportPort.exportSnapshot(expectedRevision)` capability. Runtime
  compatibility and body checksum validation remain inside
  `ChapterApplicationService`.
- `LegacyWriterNarrativeContextAdapter` uses the same explicit legacy chapter
  export adapter. It is the only writer-narrative route that can reach legacy
  local chapter reads.

`ProjectWriterNarrativeContextResolver` reads the project's authority mode and
selects exactly one adapter. It never merges adapter results and Runtime errors
are returned to the caller.

## Writer consumption

`PipelineRunner` injects the DTO before `WriterAgent.writeChapter()`. Writer
uses it for the recent narrative prompt block, chapter summaries, dialogue
fingerprints, previous ending, English variance, and long-span fatigue. The
old `WriterAgent.loadRecentChapters()` filesystem helper is removed.

Composer deliberately excludes Runtime `recent_narrative` entries from the
Writer-facing context package. The typed DTO is the sole formal recent narrative
source. Relevant memory, plot commitments, hard constraints, and style guidance
remain distinct prompt categories.

## Prohibited Runtime behavior

Runtime Writer does not enumerate `chapters/`, read chapter Markdown, read
`chapters/index.json`, infer the latest chapter from local files, combine local
and Runtime prose, or retry through the legacy adapter.
