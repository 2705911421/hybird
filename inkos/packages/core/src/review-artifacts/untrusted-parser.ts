import { Buffer } from "node:buffer";
import type { z } from "zod";

export const MAX_REVIEW_ARTIFACT_BYTES = 1_000_000;

const FORBIDDEN_KEYS = new Set([
  "command", "commands", "shell", "exec", "file_path", "filepath", "path",
  "database", "db_write", "sql", "validator_policy", "system_prompt",
]);

export class UntrustedArtifactError extends Error {
  constructor(readonly code: "too_large" | "invalid_envelope" | "invalid_json" | "forbidden_field" | "schema_invalid", message: string) {
    super(message);
    this.name = "UntrustedArtifactError";
  }
}

function controlledJsonPayload(text: string): string {
  const trimmed = text.trim();
  if (trimmed.startsWith("{") && trimmed.endsWith("}")) return trimmed;
  const fenced = trimmed.match(/^```json[ \t]*\r?\n([\s\S]*?)\r?\n```$/i);
  if (fenced?.[1]) return fenced[1].trim();
  throw new UntrustedArtifactError("invalid_envelope", "Agent output must be a JSON object or one controlled ```json fence.");
}

function assertNoCapabilities(value: unknown, pointer = "$"): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoCapabilities(item, `${pointer}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    if (FORBIDDEN_KEYS.has(key.toLowerCase())) {
      throw new UntrustedArtifactError("forbidden_field", `Agent output contains forbidden capability field ${pointer}.${key}.`);
    }
    assertNoCapabilities(child, `${pointer}.${key}`);
  }
}

export function parseUntrustedArtifact<T>(text: string, schema: z.ZodType<T>, maxBytes = MAX_REVIEW_ARTIFACT_BYTES): T {
  if (Buffer.byteLength(text, "utf8") > maxBytes) {
    throw new UntrustedArtifactError("too_large", `Agent output exceeds ${maxBytes} bytes.`);
  }
  const payload = controlledJsonPayload(text);
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch (cause) {
    throw new UntrustedArtifactError("invalid_json", `Agent output is not valid JSON: ${String(cause)}`);
  }
  assertNoCapabilities(parsed);
  const result = schema.safeParse(parsed);
  if (!result.success) {
    throw new UntrustedArtifactError("schema_invalid", `Agent artifact failed schema validation: ${result.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; ")}`);
  }
  return result.data;
}
