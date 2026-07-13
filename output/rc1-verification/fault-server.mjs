import http from "node:http";

const mode = process.argv[2];
const port = Number(process.argv[3] ?? 47931);
const now = "2026-07-14T00:00:00Z";
const items = [
  [1, "第一章：潮声", "0ffeb968ab921c6612a874ca9632ff298ac93e19b4bddb496e6551c1e44f6cda", 15],
  [2, "第二章：钥匙", "b8ea99c4533dbe44650dda84f83dbfb76fd5332e6396cf8d7ba5463c8f04c1fa", 20],
  [3, "第三章：灯塔", "68ce6320d70f6554772915a437b8e2ac33ecbbede0ae233685c05495b41c9ac9", 15],
].map(([number, title, bodyHash, characters]) => ({
  chapter_id: `00000000-0000-0000-0000-00000000000${number}`,
  chapter_number: number,
  order_key: number,
  state: "FINALIZED",
  title,
  summary: `运行时摘要${number}`,
  body_sha256: bodyHash,
  artifact_sha256: "a".repeat(64),
  character_count: characters,
  commit_id: `00000000-0000-0000-0000-00000000000${number}`,
  resulting_revision: number + 4,
  volume_id: null,
  created_at: now,
  updated_at: now,
  finalized_at: now,
}));

const server = http.createServer((request, response) => {
  if (mode === "timeout") return;

  response.setHeader("content-type", "application/json");
  if (mode === "wrong-health-version") {
    response.writeHead(200);
    if (request.url === "/api/story-runtime/v1/health") {
      response.end(JSON.stringify({ status: "ok", runtime_version: "9.9.9", schema_versions: ["story-runtime/v1"], database: "ready" }));
    } else {
      response.end(JSON.stringify({ project_id: "rc1-verification", revision: 7, finalized_only: true, total_count: 3, latest_chapter: 3, items, page: { limit: 100, has_more: false, next_cursor: null } }));
    }
    return;
  }
  if (mode === "malformed") {
    response.writeHead(200);
    response.end(JSON.stringify({ unexpected: true }));
    return;
  }
  if (mode === "version") {
    response.writeHead(409);
    response.end(JSON.stringify({ code: "VERSION_MISMATCH", message: "fault injector version mismatch", retryable: false }));
    return;
  }
  if (mode === "db-locked") {
    response.writeHead(423);
    response.end(JSON.stringify({ code: "DATABASE_LOCKED", message: "fault injector database locked", retryable: true }));
    return;
  }
  if (mode === "degraded") {
    if (request.url === "/api/story-runtime/v1/health") {
      response.writeHead(200);
      response.end(JSON.stringify({ status: "degraded", runtime_version: "0.1.0", schema_versions: ["story-runtime/v1"], database: "migration_required" }));
    } else {
      response.writeHead(503);
      response.end(JSON.stringify({ code: "RUNTIME_DEGRADED", message: "fault injector degraded", retryable: false }));
    }
    return;
  }
  response.writeHead(500);
  response.end(JSON.stringify({ code: "UNKNOWN_FAULT_MODE", message: String(mode) }));
});

server.listen(port, "127.0.0.1", () => process.stdout.write(`fault-server ${mode} ${port}\n`));
