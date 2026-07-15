# Writer Local Source Red Team

## Fixture

Runtime fixture: authority `runtime`, project revision `7`, finalized chapters
`1, 2, 3`, latest `3`. Chapter 2 and 3 are Runtime-only narrative bodies.
The deterministic Writer stub receives the prepared Writer input; no LLM is
called.

## Cases

| Case | Local projection mutation | Result |
| --- | --- | --- |
| A | No chapter Markdown | Pass |
| B | Chapter 2 body is forged | Pass |
| C | Forged future chapter 4 | Pass |
| D | Local latest/index is 99 | Pass |
| E | Local ordering differs from Runtime | Pass |
| F | Local body contains a prompt injection | Pass |

For every case the captured Writer input has revision `7`, expected revision
`7`, source `runtime`, latest chapter `3`, and ordered Runtime chapters `1..3`.
It contains no forged body, chapter 4, index value 99, or injection. The test
asserts the legacy index reader is never called and checks the Runtime export
request carries `expected_revision=7`.

## Unavailable Runtime

When Runtime export is unavailable, Writer narrative preparation rejects with a
typed Runtime-unavailable error. The resolver does not call the legacy adapter
or the local chapter reader. Existing Runtime adapter tests also cover malformed
DTO, version mismatch, authorization failure, and revision conflict.

## Static protection

The architecture gate now includes Writer, Composer, Reviser, PipelineRunner,
Continuity, long-span context, agent tools, Studio, CLI/TUI, export, analytics,
and other existing Runtime roots. It rejects Writer filesystem chapter reads,
the retired `loadRecentChapters`, a Runtime-to-legacy writer adapter branch, and
a Runner call that does not inject revision-bound narrative before writing.
