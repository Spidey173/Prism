"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

type AuditStatus = { status: string; stage: string; progress: number; error: string | null };
type Chunk = { id: string; sentence_id: string; segment_index: number; page_number: number; text: string; bboxes: number[][]; chunk_type: string; table_cells: { row: number; col: number; text: string; bbox: number[] }[]; table_bbox: number[] | null; header_row: number | null };
type PageAnnotations = { page_number: number; chunks: Chunk[] };
type Evidence = { page_number: number; bboxes: number[][]; quote: string };
type Issue = { id: string; type: string; detector: string; severity: string; status: string; title: string; explanation: string; confidence: number; needs_review: boolean; conflicting_span_a: string | null; conflicting_span_b: string | null; evidence: Evidence[] };
type Health = { score: number; high: number; med: number; low: number };

export function AuditWorkspace({ documentId }: { documentId: string }) {
  const [status, setStatus] = useState<AuditStatus | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [annotations, setAnnotations] = useState<PageAnnotations | null>(null);
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [selectedChunk, setSelectedChunk] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1.15);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");
  const [detectorFilter, setDetectorFilter] = useState("all");

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const response = await fetch(`${API_URL}/documents/${documentId}/status`);
        if (!response.ok) throw new Error("Could not read audit status.");
        const next = (await response.json()) as AuditStatus;
        if (!alive) return;
        setStatus(next);
        if (next.status === "failed") setError(next.error ?? "The document could not be processed.");
        if (next.status !== "done" && next.status !== "failed") timer = setTimeout(poll, 900);
      } catch (reason) { if (alive) setError(reason instanceof Error ? reason.message : "Could not reach the API."); }
    };
    void poll();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [documentId]);

  const refreshIssues = useCallback(async () => {
    const [issueResponse, healthResponse] = await Promise.all([
      fetch(`${API_URL}/documents/${documentId}/issues`),
      fetch(`${API_URL}/documents/${documentId}/health`),
    ]);
    if (!issueResponse.ok || !healthResponse.ok) throw new Error("Could not load audit findings.");
    setIssues((await issueResponse.json()) as Issue[]);
    const nextHealth = (await healthResponse.json()) as Health;
    setHealth(nextHealth);
  }, [documentId]);

  useEffect(() => {
    if (status?.status !== "done") return;
    const controller = new AbortController();
    setAnnotations(null);
    fetch(`${API_URL}/documents/${documentId}/pages/${pageNumber}/annotations`, { signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error("Page annotations are not available yet."); return (await response.json()) as PageAnnotations; })
      .then(setAnnotations)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not load annotations."); });
    return () => controller.abort();
  }, [documentId, pageNumber, status?.status]);

  useEffect(() => {
    if (status?.status !== "done") return;
    void refreshIssues().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load issues."));
  }, [status?.status, refreshIssues]);

  const fileUrl = useMemo(() => `${API_URL}/documents/${documentId}/file`, [documentId]);
  const showWorkspace = status?.status === "done";
  const selectedEvidence = selectedIssue?.evidence ?? [];
  const viewerPages = selectedIssue ? [...new Set(selectedEvidence.map((item) => item.page_number))] : [pageNumber];
  const visibleIssues = issues.filter((issue) => (typeFilter === "all" || issue.type === typeFilter) && (detectorFilter === "all" || (detectorFilter === "rule" ? issue.detector !== "llm_pair" : issue.detector === detectorFilter)));
  const pageChanged = useCallback((nextPage: number) => { setPageNumber(nextPage); setSelectedChunk(null); }, []);

  async function sendFeedback(issue: Issue, feedback: "confirm" | "false_positive") {
    const response = await fetch(`${API_URL}/issues/${issue.id}/feedback`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ feedback }) });
    if (!response.ok) { setError("Could not save issue feedback."); return; }
    await refreshIssues();
    setSelectedIssue(null);
  }

  function selectIssue(issue: Issue) {
    setSelectedIssue(issue);
    setSelectedChunk(null);
    setPageNumber(issue.evidence[0]?.page_number ?? 1);
  }

  return (
    <main className="workspace-shell">
      <header className="topbar"><a className="wordmark" href="/">Prism</a><div className="health-header"><span className="eyebrow">DOCUMENT HEALTH</span><strong>{health?.score ?? "—"}<small> / 100</small></strong></div><div className="run-state" aria-live="polite"><span className={`state-dot ${status?.status === "done" ? "is-done" : ""}`} />{status?.status === "done" ? "Audit complete" : status?.stage ?? "Starting audit"}</div></header>
      {!showWorkspace ? <section className="progress-card" aria-live="polite"><p className="eyebrow">DOCUMENT INTAKE</p><h1>{status?.status === "failed" ? "This PDF needs attention" : "Reading your document"}</h1><p className="muted">{error ?? "Extracting facts and checking the document for inconsistencies."}</p><div className="progress-track"><div style={{ width: `${status?.progress ?? 4}%` }} /></div><div className="stage-list"><span className={status?.stage === "parsing" ? "active" : "complete"}>01 Parse</span><span className={status?.stage === "extracting" ? "active" : status?.stage === "checking" || status?.status === "done" ? "complete" : ""}>02 Extract facts</span><span className={status?.stage === "checking" ? "active" : status?.stage === "semantic" || status?.status === "done" ? "complete" : ""}>03 Rules</span><span className={status?.stage === "semantic" ? "active" : status?.status === "done" ? "complete" : ""}>04 Semantic review</span></div>{status?.status === "failed" && <a className="text-link" href="/">Choose another PDF</a>}</section> : (
        <section className="audit-layout">
          <div className="viewer-column"><div className="document-heading"><div><p className="eyebrow">PDF PROOF</p><h1>{selectedIssue ? selectedIssue.title : "Audit findings"}</h1></div><div className="viewer-controls"><button type="button" onClick={() => pageChanged(Math.max(1, pageNumber - 1))} disabled={pageNumber <= 1}>←</button><span>Page <b>{pageNumber}</b>{pageCount ? ` / ${pageCount}` : ""}</span><button type="button" onClick={() => pageChanged(Math.min(pageCount || pageNumber + 1, pageNumber + 1))} disabled={pageCount > 0 && pageNumber >= pageCount}>→</button><label className="zoom-control">Zoom <input aria-label="PDF zoom" type="range" min="0.7" max="2" step="0.05" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /></label></div></div>
            {selectedIssue && <div className="linked-evidence" aria-live="polite">{selectedEvidence.map((item, index) => <button type="button" key={`${selectedIssue.id}-${index}`} className={item.page_number === pageNumber ? "active" : ""} onClick={() => pageChanged(item.page_number)}><span>Evidence {index + 1} · p. {item.page_number}</span><q>{item.quote}</q></button>)}</div>}
            <div className={selectedIssue ? "issue-page-stack" : ""}>{viewerPages.map((visiblePage) => <PdfPage key={`${selectedIssue?.id ?? "page"}-${visiblePage}`} fileUrl={fileUrl} pageNumber={visiblePage} zoom={zoom} chunks={visiblePage === pageNumber ? annotations?.chunks ?? [] : []} selectedChunk={selectedChunk} evidence={selectedEvidence.filter((item) => item.page_number === visiblePage)} onPageCount={setPageCount} />)}</div>
            {selectedEvidence.length > 1 && <p className="connector-note">Linked evidence {selectedEvidence.map((item) => `p. ${item.page_number}`).join(" ↔ ")}</p>}
          </div>
          <aside className="issues-panel" aria-label="Document issues"><div className="panel-heading"><p className="eyebrow">RED-PEN REVIEW</p><h2>Issues</h2><span>{visibleIssues.length} of {issues.length} findings · {health?.high ?? 0} high</span></div><div className="issue-filters"><label>Type<select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="all">All types</option>{[...new Set(issues.map((issue) => issue.type))].map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></label><label>Detector<select value={detectorFilter} onChange={(event) => setDetectorFilter(event.target.value)}><option value="all">All detectors</option><option value="rule">Rule-based</option><option value="llm_pair">AI-judged</option></select></label></div>{error && <p className="form-error" role="alert">{error}</p>}{visibleIssues.length === 0 ? <p className="empty-note">{issues.length ? "No findings match these filters." : "No issues were found. The document passed the current checks."}</p> : <ol className="issue-list">{visibleIssues.map((issue) => <li key={issue.id}><article className={`issue-card ${selectedIssue?.id === issue.id ? "selected" : ""}`}><button className="issue-select" type="button" onClick={() => selectIssue(issue)}><span className={`severity-tag ${issue.severity}`}>{issue.severity}</span><span className="issue-title">{issue.title}</span><span className="issue-meta"><span>{issue.detector === "llm_pair" ? "AI-judged" : "Rule-based"}</span><span>{Math.round(issue.confidence * 100)}% confidence</span>{issue.needs_review && <strong>Needs review</strong>}</span><span className="issue-explanation">{issue.explanation}</span>{issue.detector === "llm_pair" ? <span className="semantic-quotes">{issue.evidence.slice(0, 2).map((item, index) => <span key={`${issue.id}-${index}`}><small>Page {item.page_number}</small><q>{renderQuoteWithSpan(item.quote, index === 0 ? issue.conflicting_span_a : issue.conflicting_span_b)}</q></span>)}</span> : <span className="issue-evidence-quotes">{issue.evidence.map((item, index) => <span key={`${issue.id}-${index}`}>p. {item.page_number}: “{item.quote}”</span>)}</span>}</button>{issue.status === "open" ? <div className="feedback-actions"><button type="button" onClick={() => void sendFeedback(issue, "confirm")}>Confirm</button><button type="button" onClick={() => void sendFeedback(issue, "false_positive")}>False positive</button></div> : <p className="issue-status">Marked {issue.status.replace("_", " ")}</p>}</article></li>)}</ol>}<button className="debug-toggle" type="button" aria-expanded={debugOpen} onClick={() => setDebugOpen((open) => !open)}>{debugOpen ? "Hide" : "Show"} chunk debug panel</button>{debugOpen && <div className="debug-list">{(annotations?.chunks ?? []).map((chunk) => <button type="button" key={chunk.id} onClick={() => setSelectedChunk(chunk.id)}>{chunk.chunk_type}: {chunk.text}</button>)}</div>}</aside>
        </section>
      )}
    </main>
  );
}

function renderQuoteWithSpan(quote: string, span: string | null) {
  if (!span) return quote;
  const start = quote.toLocaleLowerCase().indexOf(span.toLocaleLowerCase());
  if (start < 0) return quote;
  return <>{quote.slice(0, start)}<mark>{quote.slice(start, start + span.length)}</mark>{quote.slice(start + span.length)}</>;
}

function PdfPage({ fileUrl, pageNumber, zoom, chunks, selectedChunk, evidence, onPageCount }: { fileUrl: string; pageNumber: number; zoom: number; chunks: Chunk[]; selectedChunk: string | null; evidence: Evidence[]; onPageCount: (count: number) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  useEffect(() => { let alive = true; setPdf(null); const loading = pdfjs.getDocument(fileUrl); loading.promise.then((loaded) => { if (!alive) { void loaded.destroy(); return; } setPdf(loaded); onPageCount(loaded.numPages); setRenderError(null); }).catch(() => { if (alive) setRenderError("Could not render this PDF."); }); return () => { alive = false; void loading.destroy(); }; }, [fileUrl, onPageCount]);
  useEffect(() => { let alive = true; let cancelRender: (() => void) | undefined; const render = async () => { if (!pdf || !canvasRef.current) return; try { const page = await pdf.getPage(pageNumber); const viewport = page.getViewport({ scale: zoom }); const canvas = canvasRef.current; const context = canvas.getContext("2d"); if (!context) return; canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height); canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`; if (!alive) return; const task = page.render({ canvasContext: context, viewport }); cancelRender = () => task.cancel(); await task.promise; } catch { if (alive) setRenderError("Could not render this PDF page."); } }; void render(); return () => { alive = false; cancelRender?.(); }; }, [pdf, pageNumber, zoom]);
  const pageChunks = chunks.filter((chunk) => chunk.chunk_type === "sentence");
  return <div className="pdf-stage">{renderError ? <p className="empty-note">{renderError}</p> : !pdf ? <p className="muted">Loading PDF…</p> : null}<div className="pdf-page-wrap" style={{ display: pdf && !renderError ? "block" : "none" }}><canvas ref={canvasRef} aria-label={`PDF page ${pageNumber}`} /><div className="highlight-layer" aria-hidden="true">{pageChunks.flatMap((chunk) => chunk.bboxes.map((bbox, index) => <span key={`${chunk.id}-${index}`} className={`highlight-rect ${selectedChunk === chunk.id ? "is-selected" : ""}`} style={{ left: `${bbox[0] * 100}%`, top: `${bbox[1] * 100}%`, width: `${(bbox[2] - bbox[0]) * 100}%`, height: `${(bbox[3] - bbox[1]) * 100}%` }} />))}{evidence.flatMap((item, evidenceIndex) => item.bboxes.map((bbox, boxIndex) => <span key={`evidence-${evidenceIndex}-${boxIndex}`} className="evidence-rect" style={{ left: `${bbox[0] * 100}%`, top: `${bbox[1] * 100}%`, width: `${(bbox[2] - bbox[0]) * 100}%`, height: `${(bbox[3] - bbox[1]) * 100}%` }} />))}{evidence.length > 1 && <svg className="issue-connector" viewBox="0 0 1000 1000">{evidence.slice(1).map((item, index) => { const first = evidence[0].bboxes[0]; const next = item.bboxes[0]; if (!first || !next) return null; return <line key={`link-${index}`} x1={((first[0] + first[2]) / 2) * 1000} y1={((first[1] + first[3]) / 2) * 1000} x2={((next[0] + next[2]) / 2) * 1000} y2={((next[1] + next[3]) / 2) * 1000} />; })}</svg>}</div></div></div>;
}
