import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { ChapterReviewArtifactSchema, HumanReviewDecisionSchema, RevisionPlanSchema, RevisionResultSchema, StateMutationProposalSchema, validateEvidenceSpan } from "../review-artifacts/schemas.js";
import { parseUntrustedArtifact, UntrustedArtifactError } from "../review-artifacts/untrusted-parser.js";
import { ReviewArtifactMapper } from "../review-artifacts/adapters.js";

const sha = (value: string) => createHash("sha256").update(value, "utf8").digest("hex");
const artifact = () => ({
  artifact_id: "a1", schema_version: "review-artifacts/v1", project_id: "p1",
  chapter_number: 1, source_revision: 0, body_sha256: sha("甲😀乙"), reviewer_kind: "reviewer",
  reviewer_version: "1", generated_at: "2026-07-12T00:00:00Z", dimensions: {}, findings: [],
  summary: "ok", recommended_action: "approve", model_metadata: {}, prompt_template_version: "review/v1",
});

describe("untrusted review artifact parsing", () => {
  it("parses the shared Python/TypeScript contract fixtures", async () => {
    const fixture = JSON.parse(await readFile(new URL("../../../../../hybrid/contracts/fixtures/review-artifacts-v1.json", import.meta.url), "utf8"));
    expect(ChapterReviewArtifactSchema.parse(fixture.chapter_review).schema_version).toBe("review-artifacts/v1");
    expect(StateMutationProposalSchema.parse(fixture.state_proposal).proposal_id).toBe("proposal-fixture");
    expect(RevisionPlanSchema.parse(fixture.revision_plan).requires_reaudit).toBe(true);
    expect(RevisionResultSchema.parse(fixture.revision_result).result_id).toBe("result-fixture");
    expect(HumanReviewDecisionSchema.parse(fixture.human_decision).decision).toBe("approve");
  });
  it("accepts pure JSON and one controlled JSON fence", () => {
    expect(parseUntrustedArtifact(JSON.stringify(artifact()), ChapterReviewArtifactSchema).artifact_id).toBe("a1");
    expect(parseUntrustedArtifact(`\`\`\`json\n${JSON.stringify(artifact())}\n\`\`\``, ChapterReviewArtifactSchema).artifact_id).toBe("a1");
  });

  it("rejects prose, fake markdown JSON, unknown fields, and malformed JSON without guessing", () => {
    expect(() => parseUntrustedArtifact(`Result:\n${JSON.stringify(artifact())}`, ChapterReviewArtifactSchema)).toThrowError(UntrustedArtifactError);
    expect(() => parseUntrustedArtifact(`\`\`\`markdown\n${JSON.stringify(artifact())}\n\`\`\``, ChapterReviewArtifactSchema)).toThrowError(/JSON object/);
    expect(() => parseUntrustedArtifact(JSON.stringify({ ...artifact(), surprise: true }), ChapterReviewArtifactSchema)).toThrowError(/schema validation/);
    expect(() => parseUntrustedArtifact('{"artifact_id":}', ChapterReviewArtifactSchema)).toThrowError(/valid JSON/);
  });

  it("rejects oversized output and embedded command, path, DB, and validator-policy capabilities", () => {
    expect(() => parseUntrustedArtifact(JSON.stringify(artifact()), ChapterReviewArtifactSchema, 10)).toThrowError(/exceeds/);
    for (const field of ["command", "file_path", "sql", "validator_policy"]) {
      expect(() => parseUntrustedArtifact(JSON.stringify({ ...artifact(), model_metadata: { [field]: "attack" } }), ChapterReviewArtifactSchema)).toThrowError(/forbidden capability/);
    }
  });

  it("uses Unicode code-point evidence offsets for CJK and surrogate pairs", () => {
    const body = "甲😀乙";
    expect(validateEvidenceSpan(body, { artifact: "chapter_body", start_offset: 1, end_offset: 2, quoted_hash: sha("😀"), locator: "1:1", explanation: "emoji", status: "current" })).toBe("current");
    expect(validateEvidenceSpan(body, { artifact: "chapter_body", start_offset: 1, end_offset: 2, quoted_hash: sha("乙"), locator: "1:1", explanation: "wrong", status: "current" })).toBe("stale");
  });

  it("merges duplicate findings without losing source confidence or inflating severity", () => {
    const finding = { finding_id: "f-a", category: "continuity", severity: "major" as const, blocking: false,
      message: "same issue", rationale: "same reason", evidence_spans: [], affected_entities: ["char-a"], affected_facts: ["location"],
      proposed_resolution: null, confidence: 0.7, source: "llm_reviewer" as const, deterministic_rule_id: null, supersedes: [], status: "open" as const };
    const first = ChapterReviewArtifactSchema.parse({ ...artifact(), findings: [finding] });
    const second = ChapterReviewArtifactSchema.parse({ ...artifact(), artifact_id: "a2", reviewer_kind: "runtime_validator", findings: [{ ...finding, finding_id: "f-b", confidence: 1, source: "runtime_validator", blocking: true }] });
    const view = ReviewArtifactMapper.toUnifiedViewModel([first, second]);
    expect(view.findings).toHaveLength(1);
    expect(view.findings[0]).toMatchObject({ severity: "major", blocking: true, sourceFindingIds: ["f-a", "f-b"] });
    expect(view.findings[0]?.confidences).toEqual([{ source: "llm_reviewer", confidence: 0.7 }, { source: "runtime_validator", confidence: 1 }]);
  });
});
