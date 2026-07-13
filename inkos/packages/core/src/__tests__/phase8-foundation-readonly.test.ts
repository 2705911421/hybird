import { describe, expect, it } from "vitest";
import { PipelineRunner } from "../pipeline/runner.js";

describe("Phase 8 foundation authority", () => {
  it("fails closed instead of rewriting long-form foundation files", async () => {
    const runner = new PipelineRunner({ projectRoot: process.cwd() } as never);

    await expect(runner.reviseFoundation("legacy-book", "change the protagonist"))
      .rejects.toThrow(/typed diff command to Story Runtime/);
  });
});
