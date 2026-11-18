"use client";

import { FormEvent, useState } from "react";
import { AuditWorkspace } from "@/components/audit-workspace";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type UploadResult = {
  id: string;
  audit_run_id: string;
  deduplicated: boolean;
  status: string;
  error: string | null;
};

export default function Home() {
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = event.currentTarget;
    const file = new FormData(form).get("file");
    if (!(file instanceof File) || !file.size) {
      setError("Choose a PDF to begin.");
      return;
    }
    setBusy(true);
    try {
      const body = new FormData();
      body.set("file", file);
      const response = await fetch(`${API_URL}/documents`, { method: "POST", body });
      const payload = await response.json();
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "The upload could not be accepted.";
        throw new Error(detail);
      }
      setUpload(payload as UploadResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reach the Prism API.");
    } finally {
      setBusy(false);
    }
  }

  if (upload) return <AuditWorkspace documentId={upload.id} />;

  return (
    <main className="landing-shell">
      <header className="landing-topbar"><span className="wordmark">Prism</span><span className="issue-count">AUTOMATIC DOCUMENT REVIEW</span></header>
      <section className="landing-content">
        <p className="eyebrow">A BETTER FIRST READ</p>
        <h1>Find what’s wrong.<br /><em>Before you ask.</em></h1>
        <p className="landing-intro">Upload a PDF to check its numbers, dates, and claims. Findings come back pinned to the evidence on the page.</p>
        <form className="upload-card" onSubmit={submit}>
          <label className="drop-area" htmlFor="pdf-upload">
            <span className="upload-mark" aria-hidden="true">↑</span>
            <strong>Choose a PDF to inspect</strong>
            <span>Text-based PDFs up to the configured size limit</span>
            <input id="pdf-upload" name="file" type="file" accept="application/pdf,.pdf" />
          </label>
          <div className="upload-actions">
            <span className="privacy-note">Your document is stored locally for this audit.</span>
            <button className="primary-button" type="submit" disabled={busy}>{busy ? "Uploading…" : "Start document audit"}</button>
          </div>
          {error && <p className="form-error" role="alert">{error}</p>}
        </form>
        <div className="landing-footnote"><span className="red-rule" />Sentence-level coordinates · Page-aware parsing · No OCR in this phase</div>
      </section>
    </main>
  );
}
