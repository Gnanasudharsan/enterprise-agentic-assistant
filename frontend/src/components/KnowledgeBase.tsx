import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, type DocumentSummary, listDocuments, uploadDocument } from "../api";
import { docType } from "../docTypes";
import { CloseIcon, DocIcon, LockIcon, SearchIcon, UploadIcon } from "./Icons";

interface Props {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
  notify: (text: string, kind?: "success" | "error") => void;
}

export function KnowledgeBase({ open, onClose, onChanged, notify }: Props) {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [query, setQuery] = useState("");
  const [type, setType] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    setLoadError(null);
    listDocuments()
      .then(setDocs)
      .catch(() => setLoadError("Couldn't load documents. Is the backend running?"));
  }, []);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const types = useMemo(() => [...new Set((docs ?? []).map((d) => d.doc_type ?? "other"))].sort(), [docs]);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (docs ?? []).filter(
      (d) =>
        (!type || (d.doc_type ?? "other") === type) &&
        (!q || `${d.doc_key} ${d.title} ${d.owner ?? ""}`.toLowerCase().includes(q)),
    );
  }, [docs, query, type]);

  async function onFile(file: File) {
    setBusy(file.name);
    try {
      const result = await uploadDocument(file);
      const verb = { created: "Added", updated: "Updated", unchanged: "Already up to date:" }[result.status];
      notify(`${verb} ${result.document.title} (${result.document.chunk_count} passages)`);
      refresh();
      onChanged();
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Upload failed.", "error");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (!open) return null;
  const passages = docs?.reduce((n, d) => n + d.chunk_count, 0) ?? 0;

  return (
    <>
      <div className="panel-scrim" onClick={onClose} />
      <aside className="panel panel-wide" role="dialog" aria-label="Knowledge base">
        <header className="panel-head">
          <div>
            <div className="panel-kicker">Knowledge base</div>
            <h2 className="panel-title">Company documents</h2>
            <p className="panel-sub">
              What the assistant can search for you. Embedded with{" "}
              <span className="mono">{docs?.[0]?.embedding_model ?? "—"}</span>
            </p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="panel-body">
          <div className="kb-stats">
            <div className="kb-stat">
              <div className="kb-stat-num">{docs?.length ?? "–"}</div>
              <div className="kb-stat-label">documents you can read</div>
            </div>
            <div className="kb-stat">
              <div className="kb-stat-num">{docs ? passages : "–"}</div>
              <div className="kb-stat-label">searchable passages</div>
            </div>
            <div className="kb-stat">
              <div className="kb-stat-num">{docs ? types.length : "–"}</div>
              <div className="kb-stat-label">document types</div>
            </div>
          </div>

          <label
            className={`dropzone ${busy ? "busy" : ""} ${drag ? "drag" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const file = e.dataTransfer.files[0];
              if (file) void onFile(file);
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".md,.markdown,.txt,.pdf,.docx"
              onChange={(e) => e.target.files?.[0] && void onFile(e.target.files[0])}
              hidden
            />
            <span className="dropzone-icon">
              <UploadIcon />
            </span>
            <span>
              {busy ? (
                <>
                  <strong>Indexing {busy}…</strong>
                  <br />
                  <small>Parsing, chunking, and embedding</small>
                </>
              ) : (
                <>
                  <strong>Upload a document</strong> or drop it here
                  <br />
                  <small>Markdown, text, PDF, or Word · up to 5 MB · shared with all employees</small>
                </>
              )}
            </span>
          </label>

          <div className="kb-tools">
            <div className="kb-search">
              <SearchIcon width={15} height={15} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter by title, ID, or owner"
                aria-label="Filter documents"
              />
            </div>
            <div className="chips" role="group" aria-label="Filter by type">
              <button type="button" className={`chip ${type === null ? "active" : ""}`} onClick={() => setType(null)}>
                All
              </button>
              {types.map((t) => {
                const meta = docType(t);
                return (
                  <button
                    key={t}
                    type="button"
                    className={`chip tone-${meta.tone} ${type === t ? "active" : ""}`}
                    onClick={() => setType(type === t ? null : t)}
                  >
                    <span className="type-dot" />
                    {meta.label}
                  </button>
                );
              })}
            </div>
          </div>

          {loadError && <p className="panel-error">{loadError}</p>}
          {!docs && !loadError && <p className="muted-text">Loading…</p>}
          {docs && visible.length === 0 && <p className="muted-text">No documents match.</p>}

          <ul className="doc-list">
            {visible.map((d) => {
              const meta = docType(d.doc_type);
              const restricted = !d.acl.includes("all-employees");
              return (
                <li key={d.id} className="doc-row">
                  <span className={`doc-row-icon tone-${meta.tone}`}>
                    <DocIcon width={16} height={16} />
                  </span>
                  <div className="doc-row-main">
                    <div className="doc-row-title">{d.title}</div>
                    <div className="doc-row-meta">
                      <span className="doc-key">{d.doc_key}</span>
                      {[meta.label, d.owner, d.version && `v${d.version}`, `${d.chunk_count} passages`]
                        .filter(Boolean)
                        .map((x) => ` · ${x}`)
                        .join("")}
                    </div>
                  </div>
                  <span className={`acl-pill ${restricted ? "restricted" : ""}`} title={`Readable by: ${d.acl.join(", ")}`}>
                    {restricted && <LockIcon width={12} height={12} />}
                    {d.acl.join(", ")}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="muted-text small">
            You only see documents your access groups can read. Restricted documents are filtered in
            the database query, before anything reaches the model.
          </p>
        </div>
      </aside>
    </>
  );
}
