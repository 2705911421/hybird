import { readdir, readFile } from "node:fs/promises";
import { dirname, extname, join, relative, resolve } from "node:path";
import ts from "../packages/core/node_modules/typescript/lib/typescript.js";

const root = resolve(import.meta.dirname, "..");
const failures = [];
const modules = new Map();

async function collect(directory) {
  for (const entry of await readdir(resolve(root, directory), { withFileTypes: true })) {
    const path = join(directory, entry.name).replaceAll("\\", "/");
    if (entry.isDirectory()) {
      if (entry.name !== "__tests__" && entry.name !== "dist" && entry.name !== "node_modules") await collect(path);
    } else if ([".ts", ".tsx"].includes(extname(entry.name)) && !entry.name.endsWith(".test.ts") && !entry.name.endsWith(".test.tsx")) {
      const text = await readFile(resolve(root, path), "utf8");
      const sourceFile = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true,
        extname(path) === ".tsx" ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
      modules.set(path, { path, text, sourceFile, imports: [], calls: [], news: [], literals: [], properties: [] });
    }
  }
}

await Promise.all([collect("packages/core/src"), collect("packages/cli/src"), collect("packages/studio/src")]);

function localImport(from, specifier) {
  if (!specifier.startsWith(".")) return undefined;
  const base = resolve(root, dirname(from), specifier);
  for (const candidate of [`${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx")]) {
    const path = relative(root, candidate).replaceAll("\\", "/");
    if (modules.has(path)) return path;
  }
  return undefined;
}

for (const module of modules.values()) {
  function visit(node) {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const names = [];
      const clause = node.importClause;
      if (clause?.name) names.push(clause.name.text);
      if (clause?.namedBindings && ts.isNamedImports(clause.namedBindings)) {
        names.push(...clause.namedBindings.elements.map((element) => element.name.text));
      }
      module.imports.push({ specifier: node.moduleSpecifier.text, names, target: localImport(module.path, node.moduleSpecifier.text) });
    }
    if (ts.isCallExpression(node)) {
      const method = ts.isPropertyAccessExpression(node.expression) ? node.expression.name.text
        : ts.isIdentifier(node.expression) ? node.expression.text : undefined;
      if (method) module.calls.push({ method, node });
    }
    if (ts.isNewExpression(node)) {
      const name = ts.isIdentifier(node.expression) ? node.expression.text : node.expression.getText(module.sourceFile);
      module.news.push({ name, node });
    }
    if (ts.isStringLiteral(node)) module.literals.push({ value: node.text, node });
    if (ts.isPropertyAssignment(node)) module.properties.push(node);
    ts.forEachChild(node, visit);
  }
  visit(module.sourceFile);
}

function line(module, node) {
  return module.sourceFile.getLineAndCharacterOfPosition(node.getStart(module.sourceFile)).line + 1;
}

function fail(module, node, message) {
  failures.push(`${module.path}:${line(module, node)} ${message}`);
}

const runtimeRoots = [
  "packages/core/src/pipeline/runner.ts",
  "packages/core/src/agents/writer.ts",
  "packages/core/src/agents/composer.ts",
  "packages/core/src/agents/reviser.ts",
  "packages/core/src/utils/long-span-fatigue.ts",
  "packages/core/src/pipeline/scheduler.ts",
  "packages/core/src/agent/context-transform.ts",
  "packages/core/src/agent/agent-tools.ts",
  "packages/core/src/agents/continuity.ts",
  "packages/core/src/utils/book-eval.ts",
  "packages/core/src/interaction/export-artifact.ts",
  "packages/studio/src/api/server.ts",
  "packages/cli/src/commands/analytics.ts",
  "packages/cli/src/commands/status.ts",
  "packages/cli/src/commands/detect.ts",
  "packages/cli/src/commands/book.ts",
  "packages/cli/src/commands/chapter.ts",
  "packages/cli/src/commands/auto.ts",
  "packages/cli/src/tui/app.ts",
  "packages/cli/src/tui/chapter-surface.ts",
];

const writer = modules.get("packages/core/src/agents/writer.ts");
if (!writer) {
  failures.push("packages/core/src/agents/writer.ts: missing production writer");
} else {
  for (const entry of writer.imports) {
    if ((entry.specifier === "node:fs" || entry.specifier === "node:fs/promises")
        && entry.names.some((name) => ["readdir", "createReadStream"].includes(name))) {
      failures.push(`${writer.path}: WriterAgent imports a chapter-directory filesystem reader`);
    }
  }
  if (writer.calls.some((call) => call.method === "loadRecentChapters")) {
    failures.push(`${writer.path}: WriterAgent reaches retired local loadRecentChapters()`);
  }
  for (const call of writer.calls) {
    if (["readFile", "readdir", "loadChapterIndex"].includes(call.method)
        && /chapters|index\.json/.test(call.node.getText(writer.sourceFile))) {
      fail(writer, call.node, `WriterAgent directly reaches local chapter authority through ${call.method}()`);
    }
  }
  if (!writer.text.includes("input.narrativeContext")) {
    failures.push(`${writer.path}: WriterAgent must consume injected typed narrative context`);
  }
}

const narrative = modules.get("packages/core/src/writer-narrative-context.ts");
if (!narrative) {
  failures.push("packages/core/src/writer-narrative-context.ts: missing writer narrative authority seam");
} else {
  for (const entry of narrative.imports) {
    if (entry.specifier === "node:fs" || entry.specifier === "node:fs/promises") {
      failures.push(`${narrative.path}: writer narrative seam must not read files directly`);
    }
  }
  for (const required of ["StoryRuntimeWriterNarrativeContextAdapter", "LegacyWriterNarrativeContextAdapter", "ProjectWriterNarrativeContextResolver"]) {
    if (!narrative.text.includes(`class ${required}`)) failures.push(`${narrative.path}: missing ${required}`);
  }
  if (!narrative.calls.some((call) => call.method === "exportSnapshot")) {
    failures.push(`${narrative.path}: Runtime writer narrative must reach revision-bound ChapterExportPort`);
  }
  for (const node of narrative.sourceFile.statements.filter(ts.isClassDeclaration)) {
    if (node.name?.text !== "ProjectWriterNarrativeContextResolver") continue;
    function inspectRuntimeBranch(child) {
      if (ts.isIfStatement(child) && child.expression.getText(narrative.sourceFile).includes('book.authorityMode === "runtime"')) {
        const text = child.thenStatement.getText(narrative.sourceFile);
        if (text.includes("this.legacy")) fail(narrative, child, "Runtime writer authority branch reaches Legacy writer adapter");
      }
      ts.forEachChild(child, inspectRuntimeBranch);
    }
    inspectRuntimeBranch(node);
  }
}

const runner = modules.get("packages/core/src/pipeline/runner.ts");
if (runner) {
  const body = runner.text;
  const narrativeLoad = body.indexOf("this.writerNarrative.load");
  const writerCall = body.indexOf("writer.writeChapter");
  if (narrativeLoad < 0 || writerCall < 0 || narrativeLoad > writerCall) {
    failures.push(`${runner.path}: revision-bound writer narrative load must dominate WriterAgent.writeChapter()`);
  }
  if (!body.slice(writerCall, writerCall + 800).includes("narrativeContext")) {
    failures.push(`${runner.path}: Runtime writer call must inject typed narrative context`);
  }
}

for (const path of runtimeRoots) {
  const module = modules.get(path);
  if (!module) {
    failures.push(`${path}: missing production root`);
    continue;
  }
  for (const call of module.calls) {
    if (["loadChapterIndex", "getNextChapterNumber", "loadDurableStoryProgress"].includes(call.method)) {
      fail(module, call.node, `forbidden local chapter authority call ${call.method}()`);
    }
  }
}

const exporter = modules.get("packages/core/src/interaction/export-artifact.ts");
for (const entry of exporter?.imports ?? []) {
  if ((entry.specifier === "node:fs" || entry.specifier === "node:fs/promises")
      && entry.names.some((name) => ["readFile", "readdir", "createReadStream"].includes(name))) {
    failures.push(`${exporter.path}: exporter imports a filesystem reader; export bodies must come from ChapterExportPort`);
  }
}
if (!exporter?.calls.some((call) => call.method === "exportSnapshot")) {
  failures.push("packages/core/src/interaction/export-artifact.ts: missing ChapterExportPort.exportSnapshot() call");
}

const requiredSurfaceBoundaries = [
  "packages/studio/src/api/server.ts",
  "packages/cli/src/commands/analytics.ts",
  "packages/cli/src/commands/status.ts",
  "packages/cli/src/commands/chapter.ts",
  "packages/cli/src/tui/chapter-surface.ts",
];
for (const path of requiredSurfaceBoundaries) {
  const module = modules.get(path);
  const importsService = module?.imports.some((entry) => entry.names.includes("ChapterApplicationService"));
  const constructsService = module?.news.some((entry) => entry.name === "ChapterApplicationService");
  if (!importsService || !constructsService) failures.push(`${path}: surface must import and construct ChapterApplicationService`);
}

const noRouteAuthorityBranching = [
  "packages/studio/src/api/server.ts",
  "packages/cli/src/commands/status.ts",
  "packages/cli/src/commands/book.ts",
  "packages/cli/src/commands/review.ts",
  "packages/cli/src/tui/app.ts",
];
for (const path of noRouteAuthorityBranching) {
  const module = modules.get(path);
  if (!module) continue;
  function inspect(node) {
    if (ts.isBinaryExpression(node)) {
      const expression = node.getText(module.sourceFile);
      if (expression.includes("storyRuntime.mode") && expression.includes("story-runtime")) {
        fail(module, node, "route-level Runtime mode branching bypasses the unified configuration boundary");
      }
    }
    ts.forEachChild(node, inspect);
  }
  inspect(module.sourceFile);
}

const service = modules.get("packages/core/src/chapter-application-service.ts");
if (!service) {
  failures.push("packages/core/src/chapter-application-service.ts: missing authority boundary");
} else {
  for (const node of service.sourceFile.statements.filter(ts.isClassDeclaration)) {
    if (node.name?.text !== "ProjectChapterAuthorityResolver") continue;
    function inspectRuntimeBranch(child) {
      if (ts.isIfStatement(child) && child.expression.getText(service.sourceFile).includes('book.authorityMode === "runtime"')) {
        const text = child.thenStatement.getText(service.sourceFile);
        if (text.includes("LegacyChapterReadAdapter")) fail(service, child, "Runtime authority branch reaches LegacyChapterReadAdapter");
      }
      ts.forEachChild(child, inspectRuntimeBranch);
    }
    inspectRuntimeBranch(node);
  }

  const adapter = service.sourceFile.statements.find((node) =>
    ts.isClassDeclaration(node) && node.name?.text === "StoryRuntimeChapterReadAdapter");
  if (!adapter || !ts.isClassDeclaration(adapter)) {
    failures.push("packages/core/src/chapter-application-service.ts: missing Runtime chapter adapter");
  } else {
    const methods = new Map(adapter.members
      .filter(ts.isMethodDeclaration)
      .map((method) => [method.name.getText(service.sourceFile), method]));
    const edges = new Map();
    for (const [name, method] of methods) {
      const targets = new Set();
      function collectCalls(node) {
        if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
            && node.expression.expression.kind === ts.SyntaxKind.ThisKeyword) {
          targets.add(node.expression.name.text);
        }
        ts.forEachChild(node, collectCalls);
      }
      collectCalls(method);
      edges.set(name, targets);
    }

    function reachableCalls(start) {
      const seenMethods = new Set();
      const calls = new Set();
      const pending = [start];
      while (pending.length) {
        const current = pending.pop();
        if (!current || seenMethods.has(current)) continue;
        seenMethods.add(current);
        const method = methods.get(current);
        if (!method) continue;
        function collect(node) {
          if (ts.isCallExpression(node)) {
            const name = ts.isPropertyAccessExpression(node.expression) ? node.expression.name.text
              : ts.isIdentifier(node.expression) ? node.expression.text : undefined;
            if (name) calls.add(name);
          }
          ts.forEachChild(node, collect);
        }
        collect(method);
        for (const target of edges.get(current) ?? []) if (methods.has(target)) pending.push(target);
      }
      return calls;
    }

    const runtimeOperations = ["list", "get", "summary", "exportSnapshot", "search", "analytics"];
    const forbiddenRuntimeCalls = new Set(["loadChapterIndex", "getNextChapterNumber", "readFile", "readdir", "computeAnalytics"]);
    for (const operation of runtimeOperations) {
      if (!methods.has(operation)) {
        failures.push(`${service.path}: Runtime adapter is missing ${operation}()`);
        continue;
      }
      const calls = reachableCalls(operation);
      if (!calls.has("assertCompatible")) {
        fail(service, methods.get(operation), `Runtime adapter ${operation}() does not reach the compatibility handshake`);
      }
      for (const forbidden of forbiddenRuntimeCalls) {
        if (calls.has(forbidden)) fail(service, methods.get(operation), `Runtime adapter ${operation}() reaches forbidden local authority call ${forbidden}()`);
      }
    }
    if (!reachableCalls("analytics").has("chapterAggregate")) {
      fail(service, methods.get("analytics"), "Runtime analytics does not reach Runtime chapterAggregate()");
    }
  }
}

const contextTransform = modules.get("packages/core/src/agent/context-transform.ts");
if (contextTransform) {
  const transformFactory = contextTransform.sourceFile.statements.find((node) =>
    ts.isFunctionDeclaration(node) && node.name?.text === "createBookContextTransform");
  const body = transformFactory?.getText(contextTransform.sourceFile) ?? "";
  const authorityCheck = body.indexOf("isRuntimeAuthorityBook");
  const localTruthRead = body.indexOf("readTruthFiles");
  if (authorityCheck < 0 || localTruthRead < 0 || authorityCheck > localTruthRead) {
    failures.push(`${contextTransform.path}: Runtime authority guard must dominate local truth-file reads`);
  }
}

const stateManager = modules.get("packages/core/src/state/manager.ts");
if (stateManager) {
  const managerClass = stateManager.sourceFile.statements.find((node) =>
    ts.isClassDeclaration(node) && node.name?.text === "StateManager");
  const bootstrap = managerClass?.members.find((node) =>
    ts.isMethodDeclaration(node) && node.name.getText(stateManager.sourceFile) === "ensureRuntimeState");
  if (!bootstrap || !bootstrap.body?.statements.some(ts.isThrowStatement)) {
    failures.push(`${stateManager.path}: ensureRuntimeState() must fail closed instead of bootstrapping from projections`);
  }
  if (bootstrap) {
    function inspectBootstrap(node) {
      if (ts.isCallExpression(node)) fail(stateManager, node, "ensureRuntimeState() must not call a projection/bootstrap reader");
      ts.forEachChild(node, inspectBootstrap);
    }
    inspectBootstrap(bootstrap);
  }
}

for (const module of modules.values()) {
  for (const literal of module.literals) {
    if (literal.value === "shadow") fail(module, literal.node, "retired shadow mode appears in production AST");
  }
  for (const property of module.properties) {
    if (property.name.getText(module.sourceFile) === "fallbackOnUnavailable") {
      fail(module, property, "retired Runtime fallback flag appears in production configuration");
    }
  }
}

if (failures.length) {
  process.stderr.write(`Runtime chapter authority gate failed:\n${failures.map((failure) => `- ${failure}`).join("\n")}\n`);
  process.exit(1);
}

const importEdges = [...modules.values()].reduce((count, module) => count + module.imports.filter((entry) => entry.target).length, 0);
const callSites = [...modules.values()].reduce((count, module) => count + module.calls.length, 0);
process.stdout.write(`Runtime chapter authority AST gate passed (${modules.size} modules, ${importEdges} import edges, ${callSites} call sites).\n`);
