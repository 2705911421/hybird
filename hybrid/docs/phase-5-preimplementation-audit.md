# Phase 5 preimplementation audit

Date: 2026-07-12

## Phase 4 entry gate

The current Runtime-authority path has a single canonical writer in Story Runtime. `ChapterCommitService` implements prepare, validate, commit, revision CAS, idempotency replay/conflict handling, durable event append and projection/outbox processing. `ChapterPersistencePort` selects the Runtime adapter only for Runtime-authority projects; legacy projects continue through legacy persistence. Runtime-authority calls bypass InkOS Truth writes and direct authority mutation tools are rejected. The current Python suite passes 48/48, including Phase 4 lifecycle, failure-matrix, recovery, migration and deterministic E2E tests. Phase 5 may proceed; the review gate remains behind `unifiedReview.enabled`.

## Existing reviewers and contracts

| Component | Input | Output before Phase 5 | Current authority/risk |
| --- | --- | --- | --- |
| `ContinuityAuditor` (`agents/continuity.ts`) | chapter text, outline, state/context | `AuditResult` with `passed`, free-text `summary`, scores and `AuditIssue[]` | TypeScript interface only; parser accepts model text and normalizes `info/warning/critical`. No durable revision/body hash or evidence offsets. |
| pipeline Auditor role | draft plus governed prompt context | same `AuditResult`; chapter index stores formatted strings in `auditIssues` | Presentation DTO is also used as a workflow gate. It is not an authoritative Runtime decision. |
| `StateValidatorAgent` (`agents/state-validator.ts`) | chapter/state context | advisory state-validation report | LLM output overlaps continuity checks and must remain advisory. |
| deterministic state validator (`state/state-validator.ts`) | structured state transitions | deterministic validation issues | Suitable for Runtime rules when backed by SQLite authority; must not be conflated with literary advice. |
| `FoundationReviewer` | foundation/architecture material | structured review result local to foundation generation | Not a chapter authority contract; mapping must be explicit if shown in the unified UI. |
| Reviewer / chapter review cycle | chapter, audit result and review-mode policy | review decision embedded in pipeline result/status | `ready-for-review`, `audit-failed`, and `approved` are legacy InkOS workflow statuses, not Runtime canonical decisions. |
| `ReviserAgent` (`agents/reviser.ts`) | original chapter, `AuditIssue[]`, mode and optional brief | `ReviseOutput`: revised content or patches plus fixed issue text | It writes revised chapter text through the pipeline. It must not write Runtime facts/Truth and its output needs a `RevisionPlan`/`RevisionResult` adapter. |
| human review in Studio/CLI/TUI | chapter metadata and audit strings | legacy chapter status/index updates | Decisions lack a revision-bound, idempotent audit record. Runtime-authority projects need `HumanReviewDecision` through Runtime API. |

## Findings for the required questions

1. **All review agents.** Chapter-facing review is performed by `ContinuityAuditor`, the pipeline Auditor/Reviewer cycle, `StateValidatorAgent`, and `ReviserAgent`; `FoundationReviewer` is adjacent but reviews foundations rather than chapter commits.
2. **Inputs and outputs.** They consume prose plus outline/state/prompt context and return TypeScript-interface objects derived from model text. Reviser returns changed prose/patches; pipeline code persists prose and flattens issues into the chapter index.
3. **Free Markdown/text.** Auditor summaries, issue descriptions/suggestions, Reviser fixed-issue text, chapter-index `auditIssues`, CLI/TUI messages and several Studio views are free text. Legacy reports may remain display-only during rollout.
4. **Existing schemas.** Book/config DTOs use Zod and agent tools use TypeBox, but the legacy `AuditResult`/`AuditIssue` contract is not the canonical cross-language schema. The new `review-artifacts/v1` JSON Schema, Pydantic models and Zod schemas must be the only commit-chain contract.
5. **Severity.** Legacy continuity uses `info`, `warning`, `critical`; some UI paths use textual errors. Phase 5 maps these to `info`, `minor`, `major`, `critical` and keeps `blocking` independent. The legacy adapter maps `warning` to `major` and only preserves legacy critical-as-blocking behavior at that boundary.
6. **Blocking representation.** Legacy uses `passed`, critical issues and `audit-failed`. Runtime uses explicit `ReviewFinding.blocking`; commit checks unresolved open blocking fingerprints. Severity alone never determines the Runtime gate.
7. **Human decisions.** Legacy approval is chapter status/index state. Phase 5 stores revision-bound `HumanReviewDecision` rows with a decision id, idempotency key, payload hash, reviewer, per-finding decisions and timestamp.
8. **Reviser input.** Reviser currently receives legacy audit issues and a natural-language brief. The Phase 5 adapter must supply a validated `RevisionPlan`, including allowed scope, locked text, hard facts and target findings.
9. **Direct writes.** Reviser/pipeline directly rewrites chapter files in the legacy path. It does not become a Runtime or Truth writer. Runtime-authority revisions produce candidate body plus typed result; only Story Runtime may accept the eventual commit.
10. **Post-revision audit.** The pipeline contains post-revision audit paths, but legacy/manual paths are not uniformly enforced. Runtime now rejects plans without `requires_reaudit`, marks prior findings stale after a body change, and the commit gate only accepts artifacts matching the revised body hash.
11. **StateValidator overlap.** Both state validation and continuity review can report entity state, location, timeline, relationship and world-rule conflicts. Deterministic checks against SQLite belong to Runtime; ambiguous inference and prose-level continuity remain LLM findings with provenance.
12. **webnovel-writer reuse.** `data_modules/chapter_commit_schema.py`, `review_schema.py`, `artifact_validator.py`, and `chapter_commit_service.py` demonstrate strict Pydantic review, fulfillment, disambiguation and extraction artifacts plus a blocking commit gate. Reuse the separation of review, planned-node fulfillment, pending disambiguation and accepted extraction proposals, but not its file/DB authority behavior.
13. **Rule allocation.** Runtime owns schema/version/scope/revision/body hash, evidence bounds/hash, IDs, mutation types, legal transitions, known entities, nonnegative resources, duplicate chapter/event, structured SQLite conflicts and unresolved blocking gates. LLMs advise on pacing, payoff, emotion, style, repetition, AI-like prose, chapter pull, characterization, viewpoint, dialogue and ambiguous semantic continuity.
14. **UI dependencies.** CLI localization/progress, analytics and revise commands consume `revised`, `fixedCount`, chapter status and flattened `auditIssues`. TUI effects/intents invoke `revise_chapter` and display the same pipeline result. Studio server/routes and tests depend on chapter status and legacy review payloads. All three need one `UnifiedReviewViewModel`; compatibility mapping may feed display, but may not create a second authoritative decision store.

## Implementation constraints derived from the audit

- Treat every model response as untrusted data. Parse only pure JSON or one controlled JSON fence, enforce a byte limit and strict schema, and reject commands/paths/policy overrides rather than guessing fields with regex.
- Store raw findings and their provenance. Aggregate by a deterministic fingerprint without severity inflation and apply human decisions to the aggregate fingerprint.
- Evidence offsets are Unicode code-point offsets across Python and TypeScript. A body revision makes old evidence stale unless explicitly remapped and hash-verified.
- `StateMutationProposal` is inert input. Agents and adapters cannot execute its mutations or call a Truth writer.
- Runtime never invokes an LLM. InkOS owns creative/review model execution and communicates only through the Runtime client.
