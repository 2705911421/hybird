import { createHash } from "node:crypto";
import { z } from "zod";

export const REVIEW_ARTIFACT_SCHEMA_VERSION = "review-artifacts/v1" as const;
const Sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const Id = z.string().min(1).max(128);

export const EvidenceSpanSchema = z.object({
  artifact: z.literal("chapter_body"), start_offset: z.number().int().nonnegative(),
  end_offset: z.number().int().positive(), quoted_hash: Sha256,
  locator: z.string().min(1).max(500), explanation: z.string().max(2_000),
  status: z.enum(["current", "stale", "remapped"]),
}).strict();

export const ReviewFindingSchema = z.object({
  finding_id: Id, category: z.string().min(1).max(100),
  severity: z.enum(["info", "minor", "major", "critical"]), blocking: z.boolean(),
  message: z.string().min(1).max(4_000), rationale: z.string().max(8_000),
  evidence_spans: z.array(EvidenceSpanSchema).max(100),
  affected_entities: z.array(Id).max(100), affected_facts: z.array(z.string().max(256)).max(100),
  proposed_resolution: z.string().max(8_000).nullable(), confidence: z.number().min(0).max(1),
  source: z.enum(["runtime_validator", "llm_reviewer", "human", "legacy_adapter"]),
  deterministic_rule_id: Id.nullable(), supersedes: z.array(Id).max(100),
  status: z.enum(["open", "accepted", "rejected", "resolved", "superseded", "stale"]),
}).strict();

export const ChapterReviewArtifactSchema = z.object({
  artifact_id: Id, schema_version: z.literal(REVIEW_ARTIFACT_SCHEMA_VERSION), project_id: Id,
  chapter_number: z.number().int().positive(), source_revision: z.number().int().nonnegative(), body_sha256: Sha256,
  reviewer_kind: z.enum(["auditor", "continuity_auditor", "state_validator", "reviewer", "runtime_validator", "human", "legacy_adapter"]),
  reviewer_version: z.string().min(1).max(100), generated_at: z.string().datetime({ offset: true }),
  dimensions: z.record(z.string(), z.number().min(0).max(100)), findings: z.array(ReviewFindingSchema).max(1_000),
  summary: z.string().max(16_000), recommended_action: z.enum(["approve", "revise", "human_review", "reject"]),
  model_metadata: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])),
  prompt_template_version: z.string().min(1).max(100),
}).strict();

const MutationSchema = z.object({ operation: z.enum(["create", "update", "delete", "resolve", "reopen"]), target_id: Id, value: z.record(z.string(), z.unknown()) }).strict();
export const StateMutationProposalSchema = z.object({
  proposal_id: Id, schema_version: z.literal(REVIEW_ARTIFACT_SCHEMA_VERSION), project_id: Id,
  chapter_number: z.number().int().positive(), source_revision: z.number().int().nonnegative(), body_sha256: Sha256,
  entity_mutations: z.array(MutationSchema).max(1_000), relationship_mutations: z.array(MutationSchema).max(1_000),
  fact_mutations: z.array(MutationSchema).max(1_000), timeline_events: z.array(MutationSchema).max(1_000),
  narrative_thread_mutations: z.array(MutationSchema).max(1_000), foreshadowing_mutations: z.array(MutationSchema).max(1_000),
  evidence: z.array(EvidenceSpanSchema), confidence: z.number().min(0).max(1),
  extraction_source: z.enum(["observer", "reflector", "chapter_analyzer", "legacy_adapter"]),
}).strict();

export const RevisionPlanSchema = z.object({
  plan_id: Id, schema_version: z.literal(REVIEW_ARTIFACT_SCHEMA_VERSION), project_id: Id,
  chapter_number: z.number().int().positive(), source_revision: z.number().int().nonnegative(), body_sha256: Sha256,
  finding_ids: z.array(Id), allowed_scopes: z.array(z.string()), forbidden_hard_facts: z.array(z.string()),
  locked_text: z.array(EvidenceSpanSchema), target_outcomes: z.array(z.string()), requires_reaudit: z.boolean(),
}).strict();

export const RevisionResultSchema = z.object({
  result_id: Id, schema_version: z.literal(REVIEW_ARTIFACT_SCHEMA_VERSION), project_id: Id,
  chapter_number: z.number().int().positive(), source_revision: z.number().int().nonnegative(),
  original_body_sha256: Sha256, revised_body_sha256: Sha256,
  resolved_finding_ids: z.array(Id), unresolved_finding_ids: z.array(Id), newly_introduced_risks: z.array(z.string()),
  changed_spans: z.array(z.object({ start_offset: z.number().int().nonnegative(), end_offset: z.number().int().nonnegative(), replacement_hash: Sha256 }).strict()),
  revision_rationale: z.string().max(16_000),
}).strict();

export const HumanReviewDecisionSchema = z.object({
  decision_id: Id, schema_version: z.literal(REVIEW_ARTIFACT_SCHEMA_VERSION), project_id: Id,
  chapter_number: z.number().int().positive(), reviewer: z.string().min(1),
  decision: z.enum(["approve", "reject", "request_changes"]),
  finding_decisions: z.record(z.string(), z.enum(["accept", "reject", "request_changes"])),
  comment: z.string().max(16_000), timestamp: z.string().datetime({ offset: true }), source_revision: z.number().int().nonnegative(),
}).strict();

export const ReviewStatusResultSchema = z.object({
  project_id: Id, chapter_number: z.number().int().positive(), revision: z.number().int().nonnegative(),
  status: z.enum(["clear", "blocked", "changes_requested", "rejected", "stale", "unreviewed"]),
  blocking_finding_ids: z.array(Id), requires_human: z.boolean(), reasons: z.array(z.string()),
}).strict();

export const ReviewValidationResultSchema = z.object({
  project_id: Id, chapter_number: z.number().int().positive(), accepted_artifact_ids: z.array(Id),
  stale_finding_ids: z.array(Id), blocking_finding_ids: z.array(Id), fingerprints: z.record(z.string(), Sha256),
  status: ReviewStatusResultSchema, replayed: z.boolean(),
}).strict();

export const RevisionDiffResultSchema = z.object({
  project_id: Id, chapter_number: z.number().int().positive(), source_revision: z.number().int().nonnegative(),
  original_body: z.string(), revised_body: z.string(), original_body_sha256: Sha256, revised_body_sha256: Sha256,
  changed_spans: RevisionResultSchema.shape.changed_spans,
}).strict();

export type ChapterReviewArtifact = z.infer<typeof ChapterReviewArtifactSchema>;
export type ReviewFinding = z.infer<typeof ReviewFindingSchema>;
export type RevisionPlan = z.infer<typeof RevisionPlanSchema>;
export type RevisionResult = z.infer<typeof RevisionResultSchema>;
export type HumanReviewDecision = z.infer<typeof HumanReviewDecisionSchema>;
export type StateMutationProposal = z.infer<typeof StateMutationProposalSchema>;
export type ReviewStatusResult = z.infer<typeof ReviewStatusResultSchema>;
export type ReviewValidationResult = z.infer<typeof ReviewValidationResultSchema>;
export type RevisionDiffResult = z.infer<typeof RevisionDiffResultSchema>;

export function validateEvidenceSpan(body: string, span: z.infer<typeof EvidenceSpanSchema>): "current" | "stale" {
  const codePoints = Array.from(body);
  if (span.end_offset <= span.start_offset || span.end_offset > codePoints.length) return "stale";
  const quoted = codePoints.slice(span.start_offset, span.end_offset).join("");
  return createHash("sha256").update(quoted, "utf8").digest("hex") === span.quoted_hash ? "current" : "stale";
}
