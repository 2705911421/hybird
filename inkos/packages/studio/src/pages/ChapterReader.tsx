import { useState } from "react";
import { fetchJson, useApi, postApi } from "../hooks/use-api";
import type { Theme } from "../hooks/use-theme";
import type { TFunction } from "../hooks/use-i18n";
import { useColors } from "../hooks/use-colors";
import {
  ChevronLeft,
  Check,
  X,
  List,
  RotateCcw,
  BookOpen,
  CheckCircle2,
  XCircle,
  Hash,
  Type,
  Clock,
  Pencil,
  Save,
  Eye,
} from "lucide-react";

interface ChapterData {
  readonly chapterNumber: number;
  readonly filename: string;
  readonly content: string;
  readonly chapter?: { readonly bodyChecksum?: string; readonly resultingRevision?: number };
}

interface ReviewFindingData {
  readonly finding_id: string; readonly category: string; readonly severity: "info" | "minor" | "major" | "critical";
  readonly blocking: boolean; readonly message: string; readonly rationale: string; readonly status: string;
  readonly source: "runtime_validator" | "llm_reviewer" | "human" | "legacy_adapter";
  readonly affected_entities: ReadonlyArray<string>; readonly affected_facts: ReadonlyArray<string>;
  readonly evidence_spans: ReadonlyArray<{ readonly start_offset: number; readonly end_offset: number; readonly locator: string; readonly explanation: string; readonly status: string }>;
}

interface RuntimeReviewData {
  readonly status: { readonly revision: number; readonly status: string; readonly reasons: ReadonlyArray<string> };
  readonly view: { readonly findings: ReadonlyArray<ReviewFindingData>; readonly deterministicFindings: ReadonlyArray<ReviewFindingData>; readonly literarySuggestions: ReadonlyArray<ReviewFindingData>; readonly hasStaleEvidence: boolean; readonly blocked: boolean; readonly blockingReasons: ReadonlyArray<string> };
  readonly revisionDiff?: { readonly original_body: string; readonly revised_body: string; readonly changed_spans: ReadonlyArray<{ readonly start_offset: number; readonly end_offset: number }> };
}

interface Nav {
  toBook: (id: string) => void;
  toDashboard: () => void;
}

export function ChapterReader({ bookId, chapterNumber, nav, theme, t }: {
  bookId: string;
  chapterNumber: number;
  nav: Nav;
  theme: Theme;
  t: TFunction;
}) {
  const c = useColors(theme);
  const { data, loading, error, refetch } = useApi<ChapterData>(
    `/books/${bookId}/chapters/${chapterNumber}`,
  );
  const { data: runtimeReview, refetch: refetchReview } = useApi<RuntimeReviewData>(`/books/${bookId}/chapters/${chapterNumber}/reviews`);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<string>("all");

  const handleStartEdit = () => {
    if (!data) return;
    setEditContent(data.content);
    setEditing(true);
  };

  const handleCancelEdit = () => {
    setEditing(false);
    setEditContent("");
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetchJson(`/books/${bookId}/chapters/${chapterNumber}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editContent }),
      });
      setEditing(false);
      refetch();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="flex flex-col items-center justify-center py-32 space-y-4">
      <div className="w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
      <span className="text-sm text-muted-foreground">{t("reader.openingManuscript")}</span>
    </div>
  );

  if (error) return <div className="text-destructive p-8 bg-destructive/5 rounded-xl border border-destructive/20">Error: {error}</div>;
  if (!data) return null;

  // Split markdown content into title and body
  const lines = data.content.split("\n");
  const titleLine = lines.find((l) => l.startsWith("# "));
  const title = titleLine?.replace(/^#\s*/, "") ?? `Chapter ${chapterNumber}`;
  const body = lines
    .filter((l) => l !== titleLine)
    .join("\n")
    .trim();

  const handleApprove = async () => {
    try {
      if (runtimeReview) {
        await submitRuntimeDecision("approve", {}, "Approved in Studio.");
        return;
      }
      await postApi(`/books/${bookId}/chapters/${chapterNumber}/approve`);
      nav.toBook(bookId);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Approve failed");
    }
  };

  const handleReject = async () => {
    try {
      if (runtimeReview) {
        await submitRuntimeDecision("reject", {}, "Rejected in Studio.");
        return;
      }
      await postApi(`/books/${bookId}/chapters/${chapterNumber}/reject`);
      nav.toBook(bookId);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Reject failed");
    }
  };

  const submitRuntimeDecision = async (
    decision: "approve" | "reject" | "request_changes",
    findingDecisions: Record<string, "accept" | "reject" | "request_changes">,
    comment: string,
  ) => {
    const decisionId = crypto.randomUUID();
    await fetchJson(`/books/${bookId}/chapters/${chapterNumber}/review-decisions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisionId, idempotencyKey: `studio-${decisionId}`, reviewer: "studio-user", decision, findingDecisions, comment }),
    });
    await refetchReview();
  };

  const paragraphs = body.split(/\n\n+/).filter(Boolean);
  const visibleFindings = runtimeReview?.view.findings.filter((finding) => severityFilter === "all" || finding.severity === severityFilter) ?? [];

  return (
    <div className="max-w-4xl mx-auto space-y-10 fade-in" data-testid="runtime-chapter-detail" data-runtime-hash={data.chapter?.bodyChecksum ?? ""} data-runtime-revision={data.chapter?.resultingRevision ?? ""}>
      {/* Navigation & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <nav className="flex items-center gap-2 text-[13px] font-medium text-muted-foreground">
          <button
            onClick={nav.toDashboard}
            className="hover:text-primary transition-colors flex items-center gap-1"
          >
            {t("bread.books")}
          </button>
          <span className="text-border">/</span>
          <button
            onClick={() => nav.toBook(bookId)}
            className="hover:text-primary transition-colors truncate max-w-[120px]"
          >
            {bookId}
          </button>
          <span className="text-border">/</span>
          <span className="text-foreground flex items-center gap-1">
            <Hash size={12} />
            {chapterNumber}
          </span>
        </nav>

        <div className="flex gap-2">
          <button
            onClick={() => nav.toBook(bookId)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold bg-secondary text-muted-foreground rounded-xl hover:text-foreground hover:bg-secondary/80 transition-all border border-border/50"
          >
            <List size={14} />
            {t("reader.backToList")}
          </button>

          {/* Edit / Preview toggle */}
          {editing ? (
            <>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold bg-primary text-primary-foreground rounded-xl hover:scale-105 active:scale-95 transition-all shadow-sm disabled:opacity-50"
              >
                {saving ? <div className="w-3.5 h-3.5 border-2 border-primary-foreground/20 border-t-primary-foreground rounded-full animate-spin" /> : <Save size={14} />}
                {saving ? t("book.saving") : t("book.save")}
              </button>
              <button
                onClick={handleCancelEdit}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold bg-secondary text-muted-foreground rounded-xl hover:text-foreground transition-all border border-border/50"
              >
                <Eye size={14} />
                {t("reader.preview")}
              </button>
            </>
          ) : !runtimeReview ? (
            <button
              onClick={handleStartEdit}
              className="flex items-center gap-2 px-4 py-2 text-xs font-bold bg-secondary text-muted-foreground rounded-xl hover:text-primary hover:bg-primary/10 transition-all border border-border/50"
            >
              <Pencil size={14} />
              {t("reader.edit")}
            </button>
          ) : null}

          <button
            onClick={handleApprove}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold bg-emerald-500/10 text-emerald-600 rounded-xl hover:bg-emerald-500 hover:text-white transition-all border border-emerald-500/20 shadow-sm"
          >
            <CheckCircle2 size={14} />
            {t("reader.approve")}
          </button>
          <button
            onClick={handleReject}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold bg-destructive/10 text-destructive rounded-xl hover:bg-destructive hover:text-white transition-all border border-destructive/20 shadow-sm"
          >
            <XCircle size={14} />
            {t("reader.reject")}
          </button>
        </div>
      </div>

      {runtimeReview && (
        <section className="rounded-2xl border border-border bg-card p-6 space-y-6" aria-label="Runtime chapter review">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold">Runtime review · {runtimeReview.status.status}</h2>
              <p className="text-xs text-muted-foreground">Deterministic errors: {runtimeReview.view.deterministicFindings.length} · Literary suggestions: {runtimeReview.view.literarySuggestions.length}</p>
            </div>
            <div className="flex gap-2">
              <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} className="rounded-lg border border-border bg-background px-3 py-2 text-xs">
                {['all', 'critical', 'major', 'minor', 'info'].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <button
                onClick={() => void submitRuntimeDecision("approve", Object.fromEntries(runtimeReview.view.findings.filter((finding) => !finding.blocking).map((finding) => [finding.finding_id, "accept"])), "Bulk-approved non-blocking findings in Studio.")}
                className="rounded-lg border border-emerald-500/30 px-3 py-2 text-xs text-emerald-600"
              >Approve non-blocking</button>
              <button onClick={() => void submitRuntimeDecision("request_changes", {}, "Revision requested in Studio.")} className="rounded-lg border border-amber-500/30 px-3 py-2 text-xs text-amber-600">Request revision</button>
            </div>
          </div>

          {(runtimeReview.status.reasons.length > 0 || runtimeReview.view.hasStaleEvidence) && (
            <div className="rounded-xl bg-destructive/5 border border-destructive/20 p-4 text-sm text-destructive">
              {runtimeReview.view.hasStaleEvidence && <div>Evidence is stale; re-audit is required.</div>}
              {runtimeReview.status.reasons.map((reason) => <div key={reason}>{reason}</div>)}
            </div>
          )}

          <div className="grid gap-4">
            {visibleFindings.map((finding) => (
              <article key={finding.finding_id} className={`rounded-xl border p-4 ${finding.source === 'runtime_validator' ? 'border-destructive/30' : 'border-primary/20'}`}>
                <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                  <span>{finding.source === 'runtime_validator' ? 'Runtime validator' : 'LLM reviewer'}</span>
                  <span className="rounded bg-secondary px-2 py-0.5">{finding.severity}</span>
                  {finding.blocking && <span className="rounded bg-destructive/10 px-2 py-0.5 text-destructive">blocking</span>}
                  <span className="text-muted-foreground">{finding.status}</span>
                </div>
                <h3 className="mt-2 font-semibold">{finding.message}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{finding.rationale}</p>
                {(finding.affected_entities.length > 0 || finding.affected_facts.length > 0) && <p className="mt-2 text-xs text-muted-foreground">Entities: {finding.affected_entities.join(', ') || 'none'} · Facts: {finding.affected_facts.join(', ') || 'none'}</p>}
                {finding.evidence_spans.map((span) => (
                  <button key={`${span.start_offset}-${span.end_offset}`} onClick={() => document.getElementById('chapter-manuscript')?.scrollIntoView({ behavior: 'smooth' })} className="mt-2 block text-left text-xs text-primary underline">
                    {span.locator} · offsets {span.start_offset}-{span.end_offset} · {span.status}: {span.explanation}
                  </button>
                ))}
                <div className="mt-3 flex gap-2">
                  <button onClick={() => void submitRuntimeDecision("approve", { [finding.finding_id]: "accept" }, `Accepted ${finding.finding_id}.`)} className="text-xs text-emerald-600">Approve</button>
                  <button onClick={() => void submitRuntimeDecision("reject", { [finding.finding_id]: "reject" }, `Rejected ${finding.finding_id}.`)} className="text-xs text-destructive">Reject</button>
                  <button onClick={() => void submitRuntimeDecision("request_changes", { [finding.finding_id]: "request_changes" }, `Revision requested for ${finding.finding_id}.`)} className="text-xs text-amber-600">Request revision</button>
                </div>
              </article>
            ))}
          </div>

          {runtimeReview.revisionDiff && (
            <div className="grid md:grid-cols-2 gap-4">
              <div><h3 className="text-sm font-bold mb-2">Before revision</h3><pre className="whitespace-pre-wrap rounded-xl bg-secondary/40 p-4 text-xs">{runtimeReview.revisionDiff.original_body}</pre></div>
              <div><h3 className="text-sm font-bold mb-2">After revision</h3><pre className="whitespace-pre-wrap rounded-xl bg-secondary/40 p-4 text-xs">{runtimeReview.revisionDiff.revised_body}</pre></div>
            </div>
          )}
        </section>
      )}

      {/* Manuscript Sheet */}
      <div id="chapter-manuscript" className="paper-sheet rounded-2xl p-8 md:p-16 lg:p-24 shadow-2xl shadow-primary/5 min-h-[80vh] relative overflow-hidden">
        {/* Physical Paper Details */}
        <div className="absolute top-0 left-8 w-px h-full bg-primary/5 hidden md:block" />
        <div className="absolute top-0 right-8 w-px h-full bg-primary/5 hidden md:block" />

        <header className="mb-16 text-center">
          <div className="flex items-center justify-center gap-2 text-muted-foreground/30 mb-8 select-none">
            <div className="h-px w-12 bg-border/40" />
            <BookOpen size={20} />
            <div className="h-px w-12 bg-border/40" />
          </div>
          <h1 className="text-4xl md:text-5xl font-serif font-medium italic text-foreground tracking-tight leading-tight">
            {title}
          </h1>
          <div className="mt-8 flex items-center justify-center gap-4 text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60">
            <span>{t("reader.manuscriptPage")}</span>
            <span className="text-border">·</span>
            <span>{chapterNumber.toString().padStart(2, '0')}</span>
          </div>
        </header>

        {editing ? (
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="w-full min-h-[60vh] bg-transparent font-serif text-lg leading-[1.8] text-foreground/90 focus:outline-none resize-none border border-border/30 rounded-lg p-6 focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all"
            autoFocus
          />
        ) : (
          <article className="prose prose-zinc dark:prose-invert max-w-none">
            {paragraphs.map((para, i) => (
              <p key={i} className="font-serif text-lg md:text-xl leading-[1.8] text-foreground/90 mb-8 first-letter:text-2xl first-letter:font-bold first-letter:text-primary/40">
                {para}
              </p>
            ))}
          </article>
        )}

        <footer className="mt-24 pt-12 border-t border-border/20 flex flex-col items-center gap-6 text-center">
          <div className="flex items-center gap-4 text-xs font-medium text-muted-foreground">
             <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary/50">
               <Type size={14} className="text-primary/60" />
               <span>{body.length.toLocaleString()} {t("reader.characters")}</span>
             </div>
             <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary/50">
               <Clock size={14} className="text-primary/60" />
               <span>{Math.ceil(body.length / 500)} {t("reader.minRead")}</span>
             </div>
          </div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground/40 font-bold">{t("reader.endOfChapter")}</p>
        </footer>
      </div>

      {/* Footer Navigation */}
      <div className="flex justify-between items-center py-8">
        {chapterNumber > 1 ? (
          <button
            onClick={() => nav.toBook(bookId)}
            className="flex items-center gap-2 text-sm font-bold text-muted-foreground hover:text-primary transition-all group"
          >
            <RotateCcw size={16} className="group-hover:-rotate-45 transition-transform" />
            {t("reader.chapterList")}
          </button>
        ) : (
          <div />
        )}
      </div>
    </div>
  );
}
