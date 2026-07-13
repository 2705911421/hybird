# InkOS Phase 7 mapping

## Sources

The scanner recognizes `inkos.json`, `books/`, book-local `story/`, `chapters/`, `story/state/*.json`, Markdown Truth/projections, manifest/current-state/hooks/summary/snapshot/outline/style files, and `memory.db`. All files are read-only and checksummed before mapping.

## Rules

| InkOS source | CIR target | Rule |
|---|---|---|
| chapter files and chapter index | `chapters` | Cross-check number and body checksum; duplicates/mismatches block. |
| structured JSON characters/world/locations/resources | `entities`, `aliases`, `facts` | JSON is a recommendation when Markdown disagrees, never a silent winner. |
| Markdown Truth/current state | `documents`, candidate facts | Bootstrap origin remains explicit provenance. |
| hooks/foreshadowing | `narrative_threads` | Known statuses map to open/resolved/deferred/abandoned; unknown transitions block. |
| chapter summaries | `summaries` | Body hash is checked where present. |
| outline/style/manifest/snapshots | `documents` and extensions | Snapshot never overwrites current state automatically. |
| `memory.db` | candidate evidence document | It cannot override chapter/structured evidence. |

Aliases are never merged on spelling alone; one alias pointing to multiple entity IDs produces `ambiguous_alias`. Resource values must be numeric and non-negative when represented as quantities. Timeline absence remains absence. Unknown JSON fields remain in attributes, extensions or `unmapped_fields`.

