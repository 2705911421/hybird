import { createHash, randomUUID } from "node:crypto";
import type { AuditIssue, AuditResult } from "../agents/continuity.js";
import type { ReviseOutput } from "../agents/reviser.js";
import {
  ChapterReviewArtifactSchema, RevisionPlanSchema, RevisionResultSchema,
  type ChapterReviewArtifact, type ReviewFinding, type ReviewStatusResult,
  type RevisionPlan, type RevisionResult,
} from "./schemas.js";

export interface UnifiedReviewViewModel {
  readonly artifactIds: ReadonlyArray<string>;
  readonly summary: string;
  readonly deterministicFindings: ReadonlyArray<UnifiedReviewFinding>;
  readonly literarySuggestions: ReadonlyArray<UnifiedReviewFinding>;
  readonly findings: ReadonlyArray<UnifiedReviewFinding>;
  readonly blocked: boolean;
  readonly blockingReasons: ReadonlyArray<string>;
  readonly hasStaleEvidence: boolean;
}

export interface UnifiedReviewFinding extends ReviewFinding {
  readonly fingerprint: string;
  readonly sources: ReadonlyArray<ReviewFinding["source"]>;
  readonly confidences: ReadonlyArray<{ readonly source: ReviewFinding["source"]; readonly confidence: number }>;
  readonly sourceFindingIds: ReadonlyArray<string>;
}

const severityRank: Record<ReviewFinding["severity"], number> = { info: 0, minor: 1, major: 2, critical: 3 };
const normalize = (value: string) => value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
export function reviewFindingFingerprint(finding: ReviewFinding): string {
  const locations = finding.evidence_spans.map((span) => `${span.start_offset}:${span.end_offset}`).join(",");
  const semantic = normalize(`${finding.message} ${finding.rationale}`).slice(0, 500);
  return createHash("sha256").update([
    finding.category, [...finding.affected_entities].map(normalize).sort().join(","),
    [...finding.affected_facts].map(normalize).sort().join(","), locations,
    finding.deterministic_rule_id ?? "", semantic,
  ].join("\0"), "utf8").digest("hex");
}

function aggregateFindings(raw: ReadonlyArray<ReviewFinding>): UnifiedReviewFinding[] {
  const groups = new Map<string, ReviewFinding[]>();
  for (const finding of raw) {
    const fingerprint = reviewFindingFingerprint(finding);
    groups.set(fingerprint, [...(groups.get(fingerprint) ?? []), finding]);
  }
  return [...groups.entries()].map(([fingerprint, findings]) => {
    const primary = findings.reduce((best, finding) => severityRank[finding.severity] > severityRank[best.severity] ? finding : best);
    const sources = [...new Set(findings.map((finding) => finding.source))];
    const statuses = findings.map((finding) => finding.status);
    const status = statuses.includes("open") ? "open" : statuses.includes("stale") ? "stale" : primary.status;
    return {
      ...primary,
      severity: primary.severity,
      blocking: findings.some((finding) => finding.blocking),
      status,
      evidence_spans: findings.flatMap((finding) => finding.evidence_spans).filter((span, index, all) => all.findIndex((candidate) => candidate.start_offset === span.start_offset && candidate.end_offset === span.end_offset && candidate.quoted_hash === span.quoted_hash) === index),
      affected_entities: [...new Set(findings.flatMap((finding) => finding.affected_entities))],
      affected_facts: [...new Set(findings.flatMap((finding) => finding.affected_facts))],
      supersedes: [...new Set(findings.flatMap((finding) => finding.supersedes))],
      fingerprint, sources,
      confidences: findings.map((finding) => ({ source: finding.source, confidence: finding.confidence })),
      sourceFindingIds: findings.map((finding) => finding.finding_id),
    };
  });
}

export class ReviewArtifactMapper {
  static toViewModel(input: unknown): UnifiedReviewViewModel {
    const artifact = ChapterReviewArtifactSchema.parse(input);
    return this.toUnifiedViewModel([artifact]);
  }

  static toUnifiedViewModel(artifacts: ReadonlyArray<ChapterReviewArtifact>, status?: ReviewStatusResult): UnifiedReviewViewModel {
    const validated = artifacts.map((artifact) => ChapterReviewArtifactSchema.parse(artifact));
    const findings = aggregateFindings(validated.flatMap((artifact) => artifact.findings));
    const deterministicFindings = findings.filter((finding) => finding.source === "runtime_validator");
    const literarySuggestions = findings.filter((finding) => finding.source !== "runtime_validator");
    const localBlocked = findings.some((finding) => finding.blocking && finding.status === "open");
    return {
      artifactIds: validated.map((artifact) => artifact.artifact_id),
      summary: validated.map((artifact) => artifact.summary).filter(Boolean).join("\n\n"),
      deterministicFindings, literarySuggestions, findings,
      blocked: status ? status.status !== "clear" : localBlocked,
      blockingReasons: status?.reasons ?? (localBlocked ? ["unresolved blocking findings"] : []),
      hasStaleEvidence: findings.some((finding) => finding.status === "stale" || finding.evidence_spans.some((span) => span.status === "stale")),
    };
  }
}

export class InkOSReviewAdapter {
  fromLegacyAudit(input: { projectId: string; chapterNumber: number; sourceRevision: number; body: string; reviewerKind: "auditor" | "continuity_auditor" | "state_validator" | "reviewer"; reviewerVersion: string; result: AuditResult }): ChapterReviewArtifact {
    const bodyHash = createHash("sha256").update(input.body, "utf8").digest("hex");
    const findings = input.result.issues.map((issue, index) => this.mapIssue(issue, index));
    return ChapterReviewArtifactSchema.parse({ artifact_id: randomUUID(), schema_version: "review-artifacts/v1", project_id: input.projectId, chapter_number: input.chapterNumber, source_revision: input.sourceRevision, body_sha256: bodyHash, reviewer_kind: input.reviewerKind, reviewer_version: input.reviewerVersion, generated_at: new Date().toISOString(), dimensions: input.result.overallScore === undefined ? {} : { overall: input.result.overallScore }, findings, summary: input.result.summary, recommended_action: findings.some((finding) => finding.blocking) ? "human_review" : findings.some((finding) => finding.severity === "major") ? "revise" : "approve", model_metadata: input.result.tokenUsage ?? {}, prompt_template_version: "legacy-audit/v1" });
  }
  private mapIssue(issue: AuditIssue, index: number): ReviewFinding {
    const severity = issue.severity === "warning" ? "major" : issue.severity;
    return { finding_id: `legacy-${index + 1}`, category: issue.category, severity, blocking: issue.severity === "critical", message: issue.description, rationale: "Mapped from the legacy InkOS audit DTO.", evidence_spans: [], affected_entities: [], affected_facts: [], proposed_resolution: issue.suggestion || null, confidence: 0.5, source: "legacy_adapter", deterministic_rule_id: null, supersedes: [], status: "open" };
  }
}

export class InkOSRevisionAdapter {
  assertReauditRequired(requiresReaudit: boolean): void { if (!requiresReaudit) throw new Error("Runtime-authority revisions must be re-audited before commit."); }

  createPlan(input: { projectId: string; chapterNumber: number; sourceRevision: number; body: string; findings: ReadonlyArray<ReviewFinding>; allowedScopes: ReadonlyArray<string>; forbiddenHardFacts: ReadonlyArray<string>; lockedText?: RevisionPlan["locked_text"]; targetOutcomes: ReadonlyArray<string> }): RevisionPlan {
    return RevisionPlanSchema.parse({
      plan_id: randomUUID(), schema_version: "review-artifacts/v1", project_id: input.projectId,
      chapter_number: input.chapterNumber, source_revision: input.sourceRevision,
      body_sha256: createHash("sha256").update(input.body, "utf8").digest("hex"),
      finding_ids: input.findings.map((finding) => finding.finding_id), allowed_scopes: [...input.allowedScopes],
      forbidden_hard_facts: [...input.forbiddenHardFacts], locked_text: input.lockedText ?? [],
      target_outcomes: [...input.targetOutcomes], requires_reaudit: true,
    });
  }

  toResult(input: { plan: RevisionPlan; originalBody: string; output: ReviseOutput }): RevisionResult {
    this.assertReauditRequired(input.plan.requires_reaudit);
    const revisedBody = input.output.revisedContent;
    const originalPoints = Array.from(input.originalBody);
    const revisedPoints = Array.from(revisedBody);
    let prefix = 0;
    while (prefix < originalPoints.length && prefix < revisedPoints.length && originalPoints[prefix] === revisedPoints[prefix]) prefix++;
    let oldSuffix = originalPoints.length;
    let newSuffix = revisedPoints.length;
    while (oldSuffix > prefix && newSuffix > prefix && originalPoints[oldSuffix - 1] === revisedPoints[newSuffix - 1]) { oldSuffix--; newSuffix--; }
    const changedSpans = input.originalBody === revisedBody ? [] : [{
      start_offset: prefix,
      end_offset: oldSuffix,
      replacement_hash: createHash("sha256").update(revisedPoints.slice(prefix, newSuffix).join(""), "utf8").digest("hex"),
    }];
    const fixed = new Set(input.output.fixedIssues);
    const resolved = input.plan.finding_ids.filter((id) => fixed.has(id));
    return RevisionResultSchema.parse({
      result_id: randomUUID(), schema_version: "review-artifacts/v1", project_id: input.plan.project_id,
      chapter_number: input.plan.chapter_number, source_revision: input.plan.source_revision,
      original_body_sha256: createHash("sha256").update(input.originalBody, "utf8").digest("hex"),
      revised_body_sha256: createHash("sha256").update(revisedBody, "utf8").digest("hex"),
      resolved_finding_ids: resolved, unresolved_finding_ids: input.plan.finding_ids.filter((id) => !resolved.includes(id)),
      newly_introduced_risks: [], changed_spans: changedSpans,
      revision_rationale: input.output.fixedIssues.join("\n"),
    });
  }
}
