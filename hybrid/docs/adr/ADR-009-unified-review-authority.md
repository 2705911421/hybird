# ADR-009: Unified review authority

Status: accepted

## Decision

Story Runtime is the sole authority for validation, effective review state, human decisions and commit eligibility of Runtime-authority projects. InkOS retains creative reviewers and Reviser, but communicates through versioned typed artifacts and centralized adapters. Studio, CLI and TUI consume one mapped review view model and never read Runtime tables or edit review JSON directly.

## Rationale

Legacy review strings combine literary advice, deterministic errors and workflow state. They cannot safely support CAS, evidence verification, deduplication, audit history or a blocking transaction gate. Typed artifacts preserve Agent provenance while allowing Runtime to distinguish deterministic facts from aesthetic suggestions.

## Consequences

- Runtime does not run creative LLMs.
- Agents may propose state but cannot mutate authority.
- Body changes invalidate evidence and force re-audit.
- Human decisions are revision-bound and idempotent.
- Legacy projects retain their old flow behind the feature flag; they do not gain a second Runtime decision store.
- Rollback disables unified review consumption but never restores Truth authority for Runtime projects.
