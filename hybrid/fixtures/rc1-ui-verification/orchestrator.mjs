#!/usr/bin/env node
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const PROJECT_ID = "rc1-ui-verification";
export const RUNTIME_REVISION = 7;
export const RUNTIME_LATEST = 3;
export const RUNTIME_PORT = 47931;
export const RUNTIME_BODY_2 = "Runtime chapter two authority sentinel.";

const NOW = "2026-07-15T00:00:00.000Z";
const BODIES = [
  "Runtime chapter one opens at the harbor.",
  RUNTIME_BODY_2,
  "Runtime chapter three closes beneath the lighthouse.",
];
const UUIDS = [
  ["10000000-0000-4000-8000-000000000001", "20000000-0000-4000-8000-000000000001"],
  ["10000000-0000-4000-8000-000000000002", "20000000-0000-4000-8000-000000000002"],
  ["10000000-0000-4000-8000-000000000003", "20000000-0000-4000-8000-000000000003"],
];

function sha(value) {
  return createHash("sha256").update(value).digest("hex");
}

function listItem(number) {
  const body = BODIES[number - 1];
  return {
    chapter_id: UUIDS[number - 1][0], chapter_number: number, order_key: number,
    state: "FINALIZED", title: `Runtime Chapter ${number}`, summary: `Runtime summary ${number}`,
    body_sha256: sha(body), artifact_sha256: sha(`artifact-${number}`), character_count: [...body].length,
    commit_id: UUIDS[number - 1][1], resulting_revision: RUNTIME_REVISION, volume_id: "v1",
    created_at: NOW, updated_at: NOW, finalized_at: NOW,
  };
}

function artifact(number) {
  const item = listItem(number);
  return {
    project_id: PROJECT_ID, chapter_id: item.chapter_id, chapter_number: number,
    revision: RUNTIME_REVISION, commit_id: item.commit_id, title: item.title,
    body: BODIES[number - 1], summary: item.summary, body_sha256: item.body_sha256,
    artifact_sha256: item.artifact_sha256, volume_id: item.volume_id,
    created_at: NOW, updated_at: NOW, finalized_at: NOW,
  };
}

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const args = { command };
  for (let index = 0; index < rest.length; index += 2) {
    args[rest[index].replace(/^--/, "")] = rest[index + 1];
  }
  return args;
}

async function writeJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function setFault(controlPath, fault) {
  await writeJson(controlPath, { fault });
}

export async function prepareFixtureProject(root, localCase = "A", options = {}) {
  const runtimePort = Number(options.runtimePort ?? RUNTIME_PORT);
  const fault = options.fault ?? "healthy";
  await rm(root, { recursive: true, force: true });
  await mkdir(join(root, "books", PROJECT_ID, "chapters"), { recursive: true });
  await writeJson(join(root, "inkos.json"), {
    name: "RC-1 UI Verification", version: "0.1.0", language: "en", languageExplicit: true,
    llm: { provider: "openai", baseUrl: "http://127.0.0.1:9/v1", apiKey: "", model: "never-called" },
    notify: [], storyRuntime: {
      mode: "story-runtime",
      baseUrl: `http://127.0.0.1:${fault === "connection_refused" ? runtimePort + 1 : runtimePort}`,
      timeoutMs: 300, maxContextTokens: 16000, maxItems: 100,
    },
  });
  await writeJson(join(root, "books", PROJECT_ID, "book.json"), {
    id: PROJECT_ID, title: "RC-1 UI Verification", platform: "other", genre: "sci-fi",
    status: "active", targetChapters: 10, chapterWordCount: 2000, authorityMode: "runtime",
    createdAt: NOW, updatedAt: NOW,
  });
  await writeJson(join(root, ".inkos", "state.json"), {
    sessionId: "rc1-ui", projectRoot: root, activeBookId: PROJECT_ID,
    automationMode: "semi", messages: [], events: [], draftRounds: [],
  });

  const chapterDir = join(root, "books", PROJECT_ID, "chapters");
  const local = {
    A: null,
    B: [],
    C: [1, 2],
    D: [1, 2, 3, 4],
    E: [1, 2, 3],
    F: [1, 2, 3],
  }[localCase];
  if (local === undefined) throw new Error(`Unknown RC-1 local case: ${localCase}`);
  if (local === null) {
    await rm(chapterDir, { recursive: true, force: true });
  } else {
    const entries = local.map((number) => ({
      number, title: `Local Chapter ${number}`, filename: `${String(number).padStart(4, "0")}_local.md`,
      status: "approved", wordCount: 1,
    }));
    await writeJson(join(chapterDir, "index.json"), localCase === "F" ? { chapters: entries, latestChapter: 99 } : entries);
    for (const entry of entries) {
      const body = entry.number === 4
        ? "# Local fake chapter 4\n\nLOCAL FAKE CHAPTER FOUR MUST NEVER APPEAR."
        : entry.number === 2 && localCase === "E"
          ? "# Local chapter 2\n\nLOCAL CONFLICTING BODY MUST NEVER APPEAR."
          : `# Local chapter ${entry.number}\n\nLocal stale body ${entry.number}.`;
      await writeFile(join(chapterDir, entry.filename), body, "utf8");
    }
  }
  const controlPath = options.controlPath ?? join(dirname(root), "runtime-control.json");
  await setFault(controlPath, fault === "connection_refused" ? "healthy" : fault);
  return { root, controlPath, localCase, fault };
}

async function readFault(controlPath) {
  try {
    return JSON.parse(await readFile(controlPath, "utf8")).fault ?? "healthy";
  } catch {
    return "healthy";
  }
}

function json(res, status, value) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(value));
}

export function startRuntimeFixtureServer({ port = RUNTIME_PORT, controlPath }) {
  const server = createServer(async (req, res) => {
    const fault = await readFault(controlPath);
    if (fault === "timeout") {
      // The product deadline is 300 ms. Finish the deliberately late fixture
      // response afterwards so the runner does not retain a poisoned socket.
      setTimeout(() => {
        if (!res.destroyed && !res.writableEnded) {
          json(res, 504, { error: { code: "TIMEOUT", message: "Runtime fixture responded after the client deadline" } });
        }
      }, 750);
      return;
    }
    if (fault === "authorization") return json(res, 401, { error: { code: "UNAUTHORIZED", message: "Runtime authorization failed" } });
    if (fault === "db_locked") return json(res, 423, { error: { code: "DATABASE_LOCKED", message: "Runtime database is locked" } });

    const url = new URL(req.url ?? "/", `http://${req.headers.host}`);
    if (url.pathname === "/health" || url.pathname === "/api/story-runtime/v1/health") {
      if (fault === "degraded") return json(res, 200, { status: "degraded", runtime_version: "0.1.0", schema_versions: ["story-runtime/v1"], database: "ready" });
      if (fault === "version_mismatch") return json(res, 200, { status: "ok", runtime_version: "9.9.9", schema_versions: ["story-runtime/v1"], database: "ready" });
      return json(res, 200, { status: "ok", runtime_version: "0.1.0", schema_versions: ["story-runtime/v1"], database: "ready" });
    }
    if (fault === "malformed_dto") return json(res, 200, { malformed: true, localFallback: "forbidden" });

    const base = `/api/story-runtime/v1/projects/${PROJECT_ID}`;
    if (url.pathname === `${base}/status`) return json(res, 200, {
      project_id: PROJECT_ID, revision: RUNTIME_REVISION, phase: "writing", latest_chapter: RUNTIME_LATEST,
      projection_health: {}, schema_version: "story-runtime/v1", active_prepare_ids: [], authority_mode: "runtime",
    });
    if (url.pathname === `${base}/chapters`) return json(res, 200, {
      project_id: PROJECT_ID, revision: RUNTIME_REVISION, finalized_only: true, total_count: 3,
      latest_chapter: 3, items: [1, 2, 3].map(listItem),
      page: { limit: Number(url.searchParams.get("limit") ?? 100), has_more: false, next_cursor: null },
    });
    const detail = new RegExp(`^${base}/chapters/(\\d+)$`).exec(url.pathname);
    if (detail && Number(detail[1]) >= 1 && Number(detail[1]) <= 3) return json(res, 200, artifact(Number(detail[1])));
    if (url.pathname === `${base}/chapter-aggregate`) return json(res, 200, {
      project_id: PROJECT_ID, revision: RUNTIME_REVISION, chapter_count: 3, latest_chapter: 3,
      total_characters: BODIES.reduce((sum, body) => sum + [...body].length, 0),
      chapters: [1, 2, 3].map((number) => ({ chapter_number: number, character_count: [...BODIES[number - 1]].length,
        volume_id: "v1", created_at: NOW, updated_at: NOW, finalized_at: NOW })),
      volumes: [{ volume_id: "v1", chapter_count: 3, character_count: BODIES.reduce((sum, body) => sum + [...body].length, 0) }],
    });
    if (url.pathname === `${base}/chapter-export`) return json(res, 200, {
      snapshot_id: randomUUID(), project_id: PROJECT_ID, revision: RUNTIME_REVISION, finalized_only: true,
      collection_sha256: sha([1, 2, 3].map((number) => `${number}:${sha(BODIES[number - 1])}`).join("\n")),
      chapter_count: 3, chapters: [1, 2, 3].map((number) => ({ ...listItem(number), body: BODIES[number - 1] })), created_at: NOW,
    });
    if (url.pathname === `${base}/chapter-search`) {
      const query = url.searchParams.get("q") ?? "";
      const matches = [1, 2, 3].filter((number) => `${BODIES[number - 1]} Runtime Chapter ${number}`.toLowerCase().includes(query.toLowerCase()));
      return json(res, 200, {
        project_id: PROJECT_ID, revision: 7, index_revision: 7, stale: false, query, total_count: matches.length,
        items: matches.map((number) => ({ ...listItem(number), body: BODIES[number - 1], snippet: BODIES[number - 1] })),
        page: { limit: 25, has_more: false, next_cursor: null },
      });
    }
    json(res, 404, { error: { code: "NOT_FOUND", message: url.pathname } });
  });
  server.listen(port, "127.0.0.1");
  return server;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const defaultRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../output/rc1-ui/project");
  const root = resolve(args.root ?? defaultRoot);
  const controlPath = resolve(args.control ?? join(dirname(root), "runtime-control.json"));
  if (args.command === "prepare") {
    const result = await prepareFixtureProject(root, args.case ?? "A", {
      runtimePort: Number(args.port ?? RUNTIME_PORT), fault: args.fault ?? "healthy", controlPath,
    });
    console.log(JSON.stringify(result));
    return;
  }
  if (args.command === "fault") {
    await setFault(controlPath, args.value ?? "healthy");
    console.log(JSON.stringify({ controlPath, fault: args.value ?? "healthy" }));
    return;
  }
  if (args.command === "serve") {
    const server = startRuntimeFixtureServer({ port: Number(args.port ?? RUNTIME_PORT), controlPath });
    console.log(`RC-1 Runtime fixture listening on ${args.port ?? RUNTIME_PORT}`);
    const stop = () => server.close(() => process.exit(0));
    process.on("SIGINT", stop);
    process.on("SIGTERM", stop);
    return;
  }
  throw new Error("Usage: orchestrator.mjs prepare|fault|serve [--root PATH] [--case A-F] [--fault NAME]");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
