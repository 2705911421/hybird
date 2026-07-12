# Phase 2/3 implementation

InkOS now reads Story Runtime only through the versioned HTTP/JSON contract. Chapter persistence, Truth files, review settlement, and Runtime write endpoints are unchanged.

## Configuration

`inkos.json`:

```json
{
  "storyRuntime": {
    "mode": "shadow",
    "baseUrl": "http://127.0.0.1:8765",
    "timeoutMs": 3000,
    "maxContextTokens": 16000,
    "maxItems": 100,
    "fallbackOnUnavailable": true
  }
}
```

Modes:

- `legacy`: use the existing Truth Context Provider only.
- `story-runtime`: query Story Runtime; on an unavailable or invalid response, use legacy when `fallbackOnUnavailable` is enabled.
- `shadow`: build both packages concurrently, use legacy for writing, and write `story/runtime/chapter-NNNN.context-shadow-diff.json`.

If Runtime authentication is enabled, set `apiTokenEnv` to an environment-variable name. Tokens are never embedded in prompts.

## Context contract

`POST /api/story-runtime/v1/queries/context` returns five explicit layers:

1. `hard_constraints`
2. `plot_commitments`
3. `relevant_memory`
4. `recent_narrative`
5. `style_guidance`

Every selected item carries a source, confidence, update time, importance, and trust label. Conflicting structured facts are returned in `conflicts`; InkOS adds a protected conflict notice and does not choose a winner. RAG text is marked untrusted and sanitized before prompt assembly.

Runtime performs exact structured retrieval before RAG, adds bounded recent summaries and active narrative threads, then compacts lower-importance items when the token budget is exceeded. InkOS retains its second-stage protected/compressible context budget.

## Observability

- `inkos status [book-id] --json` includes Runtime health and project status.
- Studio exposes `GET /api/v1/story-runtime/status` and `GET /api/v1/story-runtime/projects/:id/status`.
- `inkos compose chapter` reports conflicts and the shadow diff path.

## Deliberate Phase 2/3 boundaries

- No InkOS Agent accesses Runtime SQLite.
- No Python module is imported into InkOS.
- No Runtime private path or table name is used by InkOS.
- All Runtime responses pass strict Zod validation.
- `StoryRuntimeClient` exposes read operations only.
- Existing chapter persistence and Truth state updates remain authoritative in InkOS.
- Runtime write endpoints remain disabled; Phase 4 has not started.

## Verification

Coverage includes public contract validation, budget compaction, conflicting facts, unavailable fallback, malformed responses, prompt-injection sanitization, a 2,000-fact long-novel fixture, shadow diffs, legacy regression, and Windows subprocess lifecycle.
