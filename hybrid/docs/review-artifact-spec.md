# Review artifact specification

Canonical version: `review-artifacts/v1`

The normative machine contract is `contracts/schemas/review-artifacts.json`. Story Runtime mirrors it with strict Pydantic models in `story_runtime.contracts`; InkOS mirrors it with strict Zod schemas in `review-artifacts/schemas.ts`. Unknown fields are rejected. A version change requires a new schema identifier and explicit adapter; it may not silently reinterpret v1.

## Artifact family

- `ChapterReviewArtifact` binds one reviewer and its findings to project, chapter, source revision and UTF-8 body SHA-256. Reviewer provenance, model metadata and prompt-template version are mandatory.
- `ReviewFinding` separates `severity` (`info`, `minor`, `major`, `critical`) from `blocking`. Runtime deterministic findings use `source=runtime_validator` and a rule id. Literary findings use `source=llm_reviewer`; Runtime never presents them as facts.
- `EvidenceSpan` addresses Unicode code points, not UTF-16 code units or UTF-8 bytes. `quoted_hash` is SHA-256 of the referenced UTF-8 substring. Its status is explicitly `current`, `stale` or `remapped`.
- `StateMutationProposal` is inert. It groups proposed entity, relationship, fact, timeline, narrative-thread and foreshadowing changes. No Agent may execute it or write SQLite/Truth.
- `RevisionPlan` binds target findings, allowed scopes, forbidden hard facts, locked evidence and outcomes to the original revision/body. Runtime-authority plans require re-audit.
- `RevisionResult` binds original/revised hashes, resolved/unresolved finding ids, new risks, code-point changed spans and rationale. It is not permission to commit.
- `HumanReviewDecision` is revision-bound, idempotent and auditable. Overall and per-finding decisions are stored by Runtime.

## Evidence validation

For every span Runtime verifies `0 <= start < end <= codePointLength(body)` and `sha256(body[start:end]) == quoted_hash`. Invalid evidence is stored as stale for audit visibility and makes review status stale; it cannot clear the commit gate. A revision marks prior evidence stale. Only a newly validated artifact for the revised body hash restores eligibility.

## Finding aggregation

The fingerprint hashes category, normalized affected entities/facts, evidence locations, deterministic rule id and a normalized semantic signature. Source findings remain immutable audit rows. Aggregation does not raise severity because multiple reviewers repeat a finding. Human per-finding decisions update every source row sharing the aggregate fingerprint.

## Trust boundary

LLM output is untrusted. InkOS accepts only a pure JSON object or exactly one `json` fenced object, enforces a 1 MB limit, rejects command/path/DB/policy capability fields, parses with `JSON.parse`, and then applies the strict Zod schema. It never regex-recovers missing fields. Story Runtime applies Pydantic and domain/evidence validation again and never invokes an LLM.

## Gate semantics

`critical` does not imply `blocking`, and a lower severity may be blocking when a deterministic contract requires it. Commit requires at least one validated review artifact matching project/chapter/revision/body, no stale evidence, no effective reject/request-changes decision and no unresolved blocking aggregate unless a valid human approval explicitly resolves the gate.
