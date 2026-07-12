import type { z } from "zod";
import { randomUUID } from "node:crypto";
import {
  ContextQueryResultSchema,
  HealthResponseSchema,
  ProjectStatusResponseSchema,
  STORY_RUNTIME_SCHEMA_VERSION,
  type RuntimeContextResult,
  type RuntimeHealth,
  type RuntimeProjectStatus,
} from "./schemas.js";

export class StoryRuntimeClientError extends Error {
  constructor(
    message: string,
    readonly code: "unavailable" | "http_error" | "malformed_response",
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = "StoryRuntimeClientError";
  }
}

export interface StoryRuntimeClientOptions {
  readonly baseUrl: string;
  readonly timeoutMs?: number;
  readonly apiToken?: string;
  readonly fetchImpl?: typeof fetch;
}

export interface QueryContextInput {
  readonly projectId: string;
  readonly chapterNumber: number;
  readonly intent: string;
  readonly entityIds?: ReadonlyArray<string>;
  readonly maxTokens: number;
  readonly maxItems: number;
  readonly includeRetrievalCandidates?: boolean;
}

export class StoryRuntimeClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly apiToken?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: StoryRuntimeClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 3_000;
    this.apiToken = options.apiToken;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
  }

  health(): Promise<RuntimeHealth> {
    return this.request("/api/story-runtime/v1/health", HealthResponseSchema);
  }

  projectStatus(projectId: string): Promise<RuntimeProjectStatus> {
    return this.request(
      `/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}/status`,
      ProjectStatusResponseSchema,
    );
  }

  queryContext(input: QueryContextInput): Promise<RuntimeContextResult> {
    return this.request("/api/story-runtime/v1/queries/context", ContextQueryResultSchema, {
      method: "POST",
      body: JSON.stringify({
        request_id: randomUUID(),
        project_id: input.projectId,
        schema_version: STORY_RUNTIME_SCHEMA_VERSION,
        chapter_number: input.chapterNumber,
        intent: input.intent,
        entity_ids: input.entityIds ?? [],
        budget: { max_tokens: input.maxTokens, max_items: input.maxItems },
        include_retrieval_candidates: input.includeRetrievalCandidates ?? true,
      }),
    });
  }

  private async request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let response: Response;
      try {
        response = await this.fetchImpl(`${this.baseUrl}${path}`, {
          ...init,
          signal: controller.signal,
          headers: {
            accept: "application/json",
            ...(init?.body ? { "content-type": "application/json" } : {}),
            ...(this.apiToken ? { authorization: `Bearer ${this.apiToken}` } : {}),
            ...init?.headers,
          },
        });
      } catch (error) {
        throw new StoryRuntimeClientError(`Story Runtime is unavailable: ${String(error)}`, "unavailable", error);
      }
      if (!response.ok) {
        throw new StoryRuntimeClientError(
          `Story Runtime returned HTTP ${response.status}: ${(await response.text()).slice(0, 500)}`,
          "http_error",
        );
      }
      let payload: unknown;
      try {
        payload = await response.json();
      } catch (error) {
        throw new StoryRuntimeClientError("Story Runtime returned non-JSON data", "malformed_response", error);
      }
      const parsed = schema.safeParse(payload);
      if (!parsed.success) {
        throw new StoryRuntimeClientError(
          `Story Runtime response failed schema validation: ${parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; ")}`,
          "malformed_response",
        );
      }
      return parsed.data;
    } finally {
      clearTimeout(timer);
    }
  }
}
