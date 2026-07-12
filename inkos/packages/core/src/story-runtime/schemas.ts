import { z } from "zod";

export const STORY_RUNTIME_SCHEMA_VERSION = "story-runtime/v1" as const;

export const StoryRuntimeModeSchema = z.enum(["legacy", "story-runtime", "shadow"]);
export type StoryRuntimeMode = z.infer<typeof StoryRuntimeModeSchema>;

export const StoryRuntimeConfigSchema = z.object({
  mode: StoryRuntimeModeSchema.default("legacy"),
  baseUrl: z.string().url().default("http://127.0.0.1:8765"),
  apiTokenEnv: z.string().min(1).optional(),
  timeoutMs: z.number().int().min(100).max(60_000).default(3_000),
  maxContextTokens: z.number().int().min(256).max(100_000).default(16_000),
  maxItems: z.number().int().min(1).max(500).default(100),
  fallbackOnUnavailable: z.boolean().default(true),
}).strict().default({ mode: "legacy" });

export type StoryRuntimeConfig = z.infer<typeof StoryRuntimeConfigSchema>;

export const HealthResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "unavailable"]),
  runtime_version: z.string(),
  schema_versions: z.array(z.string()),
  database: z.enum(["ready", "locked", "migration_required", "unavailable"]),
}).strict();

export const ProjectStatusResponseSchema = z.object({
  project_id: z.string(),
  revision: z.number().int().nonnegative(),
  phase: z.string(),
  latest_chapter: z.number().int().nonnegative(),
  projection_health: z.record(z.unknown()),
  schema_version: z.string(),
  active_prepare_ids: z.array(z.string()),
}).strict();

export const ContextLayerNameSchema = z.enum([
  "hard_constraints",
  "plot_commitments",
  "relevant_memory",
  "recent_narrative",
  "style_guidance",
]);
export type ContextLayerName = z.infer<typeof ContextLayerNameSchema>;

export const ContextItemSchema = z.object({
  item_id: z.string().min(1),
  layer: ContextLayerNameSchema,
  content: z.string(),
  source: z.object({
    kind: z.enum(["structured_query", "rag", "chapter_summary", "request_intent"]),
    id: z.string().min(1),
  }).strict(),
  confidence: z.number().min(0).max(1),
  updated_at: z.string().datetime({ offset: true }),
  importance: z.number().int().min(0).max(100),
  trust: z.enum(["trusted", "untrusted_content"]),
  subject: z.string().nullable(),
  predicate: z.string().nullable(),
}).strict();

export const ContextLayersSchema = z.object({
  hard_constraints: z.array(ContextItemSchema),
  plot_commitments: z.array(ContextItemSchema),
  relevant_memory: z.array(ContextItemSchema),
  recent_narrative: z.array(ContextItemSchema),
  style_guidance: z.array(ContextItemSchema),
}).strict();

export const ContextConflictSchema = z.object({
  conflict_id: z.string(),
  subject: z.string(),
  predicate: z.string(),
  item_ids: z.array(z.string()).min(2),
  values: z.array(z.unknown()).min(2),
  message: z.string(),
}).strict();

export const ContextQueryResultSchema = z.object({
  request_id: z.string().uuid(),
  project_id: z.string(),
  revision: z.number().int().nonnegative(),
  authoritative_facts: z.array(z.unknown()),
  retrieval_candidates: z.array(z.unknown()),
  untrusted_materials: z.array(z.record(z.unknown())),
  layers: ContextLayersSchema,
  conflicts: z.array(ContextConflictSchema),
  trace: z.object({
    budget_used: z.number().int().nonnegative(),
    selected_source_ids: z.array(z.string()),
  }).strict(),
}).strict();

export type RuntimeHealth = z.infer<typeof HealthResponseSchema>;
export type RuntimeProjectStatus = z.infer<typeof ProjectStatusResponseSchema>;
export type RuntimeContextResult = z.infer<typeof ContextQueryResultSchema>;
export type RuntimeContextItem = z.infer<typeof ContextItemSchema>;
export type RuntimeContextConflict = z.infer<typeof ContextConflictSchema>;
