import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Download, FolderOpen, Pause, Play, RotateCcw, ShieldCheck } from "lucide-react";
import { fetchJson, postApi, useApi } from "../hooks/use-api";
import { tr } from "../lib/app-language";

type Conflict = {
  conflict_id: string; type: string; severity: string; blocking: boolean;
  sources: ReadonlyArray<Record<string, unknown>>; candidates: ReadonlyArray<Record<string, unknown>>;
  evidence: Record<string, unknown>; recommended_decision: string; user_decision: Record<string, unknown> | null;
};
type Job = {
  migration_job_id: string; source_type: string; target_project_id: string; current_stage: string; progress: number;
  discovery: Record<string, unknown>; source_checksum_manifest: ReadonlyArray<Record<string, unknown>>;
  conflicts: ReadonlyArray<Conflict>; decisions: Record<string, unknown>; warnings: ReadonlyArray<Record<string, unknown>>;
  cir: Record<string, unknown> | null; dry_run: Record<string, unknown> | null; target_snapshot: Record<string, unknown> | null;
  verification: Record<string, unknown> | null; cutover_confirmed: boolean;
};

const stages = ["DISCOVERED", "SCANNED", "MAPPED", "VALIDATED", "AWAITING_DECISIONS", "READY", "IMPORTING", "VERIFYING", "COMPLETED"];

export function LegacyMigrationWizard({ projectId }: { readonly projectId: string }) {
  const jobs = useApi<{ items: ReadonlyArray<Job> }>(`/story-runtime/migration-jobs?targetProjectId=${encodeURIComponent(projectId)}`);
  const [sourcePath, setSourcePath] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [longRunning, setLongRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [choices, setChoices] = useState<Record<string, { decision: "choose_candidate" | "merge" | "ignore" | "quarantine"; candidate_id?: string }>>({});

  const active = job ?? jobs.data?.items[0] ?? null;
  useEffect(() => {
    if (!longRunning || !active) return;
    const timer = window.setInterval(() => { void fetchJson<Job>(`/story-runtime/migration-jobs/${active.migration_job_id}`).then(setJob).catch(() => undefined); }, 1_000);
    return () => window.clearInterval(timer);
  }, [longRunning, active?.migration_job_id]);
  const run = async (action: string, confirmation?: string) => {
    if (!active) return;
    setBusy(true); setError(null);
    try {
      const updated = await postApi<Job>(`/story-runtime/migration-jobs/${active.migration_job_id}/${action}`, { confirmation });
      setJob(updated);
      if (action === "resume" && updated.current_stage === "IMPORTING") {
        setLongRunning(true);
        void postApi<Job>(`/story-runtime/migration-jobs/${updated.migration_job_id}/import`, { confirmation: null })
          .then(setJob).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
          .finally(() => setLongRunning(false));
      }
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const create = async () => {
    if (!sourcePath.trim()) return;
    setBusy(true); setError(null);
    try { setJob(await postApi<Job>("/story-runtime/migration-jobs", { sourcePath: sourcePath.trim(), targetProjectId: projectId, sourceType: "auto" })); await jobs.refetch(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const startImport = () => {
    if (!active || longRunning) return;
    setLongRunning(true); setError(null);
    void postApi<Job>(`/story-runtime/migration-jobs/${active.migration_job_id}/import`, { confirmation: null })
      .then(setJob).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
      .finally(() => setLongRunning(false));
  };
  const decide = async () => {
    if (!active) return;
    const decisions = active.conflicts.filter((conflict) => !conflict.user_decision && choices[conflict.conflict_id]).map((conflict) => ({
      conflict_id: conflict.conflict_id, ...choices[conflict.conflict_id], note: "Reviewed in InkOS Studio Phase 7 wizard",
    }));
    if (!decisions.length) { setError(tr("请逐项处理冲突；没有危险的“全部跳过”选项。", "Review conflicts individually; there is no unsafe skip-all action.")); return; }
    setBusy(true); setError(null);
    try { setJob(await postApi<Job>(`/story-runtime/migration-jobs/${active.migration_job_id}/decisions`, { decisions })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  return <div className="space-y-6">
    <section className="border border-border p-5">
      <div className="flex items-center gap-2"><FolderOpen size={18} /><h2 className="font-medium">{tr("1. 选择只读源目录", "1. Select read-only source directory")}</h2></div>
      <p className="mt-2 text-sm text-muted-foreground">{tr("Runtime 只扫描此路径；不执行脚本、不写源目录、不删除旧文件。", "Runtime scans this path only; it executes no scripts, writes no source files, and deletes nothing.")}</p>
      <div className="mt-4 flex gap-2"><input aria-label="Migration source directory" value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="C:\\path\\to\\legacy-project" className="min-w-0 flex-1 border border-border bg-transparent px-3 py-2 text-sm" /><button disabled={busy || !sourcePath.trim()} onClick={() => void create()} className="border border-border px-4 py-2 text-sm disabled:opacity-40">{tr("识别项目", "Discover")}</button></div>
    </section>

    {active && <>
      <section className="border border-border p-5">
        <div className="flex items-center justify-between"><div><h2 className="font-medium">{tr("2–4. 识别、扫描与校验", "2–4. Discover, scan and validate")}</h2><p className="mt-1 text-xs text-muted-foreground">{active.migration_job_id}</p></div><Stage value={active.current_stage} /></div>
        <div className="mt-4 h-2 bg-muted"><div className="h-full bg-primary" style={{ width: `${active.progress}%` }} /></div>
        <div className="mt-4 flex flex-wrap gap-2"><button disabled={busy || !["DISCOVERED", "FAILED", "SCANNED", "MAPPED", "VALIDATED", "AWAITING_DECISIONS", "READY"].includes(active.current_stage)} onClick={() => void run("scan")} className="border border-border px-4 py-2 text-sm disabled:opacity-40">{tr("扫描并生成 CIR", "Scan and build CIR")}</button><span className="self-center text-sm text-muted-foreground">{String(active.discovery.detected_type ?? active.source_type)} · {active.source_checksum_manifest.length} files</span></div>
        <div className="mt-4 grid gap-1 text-xs text-muted-foreground sm:grid-cols-3">{stages.map((stage) => <span key={stage} className={stage === active.current_stage ? "font-medium text-foreground" : ""}>{stage}</span>)}</div>
      </section>

      {active.source_checksum_manifest.length > 0 && <details className="border border-border p-5"><summary className="cursor-pointer font-medium">{tr("5. 文件清单与 SHA-256", "5. File manifest and SHA-256")}</summary><div className="mt-4 max-h-72 overflow-auto text-xs">{active.source_checksum_manifest.map((item) => <div key={String(item.path)} className="grid grid-cols-[1fr_auto] gap-4 border-b border-border py-2"><span className="break-all">{String(item.path)}</span><span className="font-mono">{String(item.sha256 ?? item.parse_status)}</span></div>)}</div></details>}

      {active.conflicts.length > 0 && <section className="border border-amber-500/40 p-5"><div className="flex items-center gap-2"><AlertTriangle className="text-amber-600" size={18} /><h2 className="font-medium">{tr("6–7. Mapping coverage 与逐项冲突决策", "6–7. Mapping coverage and individual conflict decisions")}</h2></div><p className="mt-2 text-sm text-muted-foreground">{tr("建议仅供参考；不会自动选择最新文件，也没有“跳过所有冲突”。", "Recommendations are advisory; newest-file wins and skip-all are not available.")}</p><div className="mt-4 space-y-3">{active.conflicts.map((conflict) => <div key={conflict.conflict_id} className="border border-border p-4 text-sm"><div className="flex justify-between gap-3"><strong>{conflict.type}</strong><span>{conflict.severity}{conflict.blocking ? " · blocking" : ""}</span></div><pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{JSON.stringify({ sources: conflict.sources, candidates: conflict.candidates, evidence: conflict.evidence }, null, 2)}</pre>{conflict.user_decision ? <div className="mt-3 text-emerald-700"><CheckCircle2 className="mr-1 inline" size={15} />{tr("已记录人工决策", "Human decision recorded")}</div> : <div className="mt-3 grid gap-2 sm:grid-cols-[180px_1fr]"><select aria-label={`Decision ${conflict.conflict_id}`} value={choices[conflict.conflict_id]?.decision ?? ""} onChange={(event) => setChoices((current) => ({ ...current, [conflict.conflict_id]: { decision: event.target.value as "choose_candidate" | "merge" | "ignore" | "quarantine" } }))} className="border border-border bg-card px-2 py-2"><option value="">{tr("选择处理方式", "Choose decision")}</option><option value="choose_candidate">choose_candidate</option><option value="merge">merge</option><option value="ignore">ignore</option><option value="quarantine">quarantine</option></select>{choices[conflict.conflict_id]?.decision === "choose_candidate" && <select aria-label={`Candidate ${conflict.conflict_id}`} value={choices[conflict.conflict_id]?.candidate_id ?? ""} onChange={(event) => setChoices((current) => ({ ...current, [conflict.conflict_id]: { ...current[conflict.conflict_id]!, candidate_id: event.target.value } }))} className="border border-border bg-card px-2 py-2"><option value="">{tr("选择候选值", "Choose candidate")}</option>{conflict.candidates.map((candidate) => <option key={String(candidate.candidate_id)} value={String(candidate.candidate_id)}>{String(candidate.candidate_id)}</option>)}</select>}</div>}</div>)}</div><button disabled={busy} onClick={() => void decide()} className="mt-4 border border-border px-4 py-2 text-sm disabled:opacity-40">{tr("保存已选择的决策", "Save selected decisions")}</button></section>}

      <section className="border border-border p-5"><h2 className="font-medium">{tr("8–13. Dry-run、快照、导入与验证", "8–13. Dry-run, snapshot, import and verify")}</h2><div className="mt-4 flex flex-wrap gap-2"><Action disabled={busy || longRunning || !["READY", "AWAITING_DECISIONS"].includes(active.current_stage)} onClick={() => run("dry-run")} label="Dry-run" /><Action disabled={busy || longRunning || active.current_stage !== "READY"} onClick={() => run("snapshot")} label={tr("创建已验证快照", "Create verified snapshot")} /><Action disabled={busy || longRunning || active.current_stage !== "READY" || !active.target_snapshot} onClick={startImport} label={tr("开始迁移", "Start import")} /><Action disabled={busy || longRunning || active.current_stage !== "VERIFYING"} onClick={() => run("verify")} label={tr("验证", "Verify")} />{active.current_stage === "PAUSED" ? <Action disabled={busy || longRunning} onClick={() => run("resume")} label={tr("恢复", "Resume")} icon={<Play size={15} />} /> : <Action disabled={busy || ["COMPLETED", "ROLLED_BACK"].includes(active.current_stage)} onClick={() => run("pause")} label={tr("安全暂停", "Safe pause")} icon={<Pause size={15} />} />}</div>{active.dry_run && <Report title="Dry-run" value={active.dry_run} />}{active.verification && <Report title={tr("验收指标", "Acceptance metrics")} value={active.verification} />}</section>

      <section className="border border-border p-5"><h2 className="font-medium">{tr("14–15. 用户确认 cutover 与报告", "14–15. User-confirmed cutover and report")}</h2><p className="mt-2 text-sm text-muted-foreground">{tr("只有 COMPLETED 才能确认；确认后 Runtime 成为唯一 authority。", "Confirmation is enabled only after COMPLETED; Runtime then becomes the only authority.")}</p><div className="mt-4 flex flex-wrap gap-2"><button disabled={busy || active.current_stage !== "COMPLETED" || active.cutover_confirmed} onClick={() => { if (window.confirm(tr("确认切换到 Runtime 单一 authority？旧文件不会删除。", "Confirm Runtime as the single authority? Legacy files will not be deleted."))) void run("cutover", "CONFIRM_RUNTIME_CUTOVER"); }} className="inline-flex items-center gap-2 border border-emerald-600 px-4 py-2 text-sm text-emerald-700 disabled:opacity-40"><ShieldCheck size={16} />{tr("确认 cutover", "Confirm cutover")}</button><button disabled={busy || active.cutover_confirmed || !active.target_snapshot} onClick={() => { if (window.confirm(tr("恢复迁移前目标快照？", "Restore the pre-migration target snapshot?"))) void run("rollback"); }} className="inline-flex items-center gap-2 border border-destructive/40 px-4 py-2 text-sm text-destructive disabled:opacity-40"><RotateCcw size={16} />{tr("回滚目标", "Rollback target")}</button><a href={`/api/v1/story-runtime/migration-jobs/${encodeURIComponent(active.migration_job_id)}/report`} download className="inline-flex items-center gap-2 border border-border px-4 py-2 text-sm"><Download size={16} />{tr("下载报告", "Download report")}</a></div></section>
    </>}
    {error && <div role="alert" className="border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">{error}</div>}
  </div>;
}

function Stage({ value }: { readonly value: string }) { return <span className="border border-border px-2 py-1 text-xs font-medium">{value}</span>; }
function Action({ label, disabled, onClick, icon }: { readonly label: string; readonly disabled: boolean; readonly onClick: () => void | Promise<void>; readonly icon?: ReactNode }) { return <button disabled={disabled} onClick={() => void onClick()} className="inline-flex items-center gap-2 border border-border px-4 py-2 text-sm disabled:opacity-40">{icon}{label}</button>; }
function Report({ title, value }: { readonly title: string; readonly value: Record<string, unknown> }) { return <details className="mt-4 border border-border p-4"><summary className="cursor-pointer font-medium">{title}</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(value, null, 2)}</pre></details>; }
