import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, type DocumentSummary, listDocuments, uploadDocument } from "../api";
import { CloseIcon, DocIcon, LockIcon, UploadIcon } from "./Icons";

interface Props {
  open: boolean;
  onClose: () => void;
}

type UploadState = { kind: "idle" } | { kind: "busy"; name: string } | { kind: "done" | "error"; text: string };

export function KnowledgeBase({ open, onClose }: Props) {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadState>({ kind: "idle" });
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

  async function onFile(file: File) {
    setUpload({ kind: "busy", name: file.name });
    try {
      const result = await uploadDocument(file);
      const verb = { created: "Added", updated: "Updated", unchanged: "Already up to date:" }[
        result.status
      ];
      setUpload({
        kind: "done",
        text: `${verb} ${result.document.title} (${result.document.chunk_count} passages).`,
      });
      refresh();
    } catch (e) {
      setUpload({ kind: "error", text: e instanceof ApiError ? e.message : "Upload failed." });
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (!open) return null;
  const totalChunks = docs?.reduce((n, d) => n + d.chunk_count, 0) ?? 0;

  return (
    <>
      <div className="panel-scrim" onClick={onClose} />
      <aside className="panel panel-wide" aria-label="Knowledge base">
        <header className="panel-head">
          <div>
            <div className="panel-kicker">Knowledge base</div>
            <h2 className="panel-title">Company documents</h2>
            {docs && (
              <p className="panel-sub">
                {docs.length} documents · {totalChunks} searchable passages · embedded with{" "}
                <span className="mono">{docs[0]?.embedding_model ?? "—"}</span>
              </p>
            )}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="panel-body">
          <label
            className={`dropzone ${upload.kind === "busy" ? "busy" : ""}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
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
            <UploadIcon />
            <span>
              {upload.kind === "busy" ? (
                <>Indexing {upload.name}…</>
              ) : (
                <>
                  <strong>Upload a document</strong> or drop it here
                  <br />
                  <small>Markdown, text, PDF, or Word · up to 5 MB · shared with all employees</small>
                </>
              )}
            </span>
          </label>
          {(upload.kind === "done" || upload.kind === "error") && (
            <p className={`upload-msg ${upload.kind}`}>{upload.text}</p>
          )}

          {loadError && <p className="panel-error">{loadError}</p>}
          {!docs && !loadError && <p className="muted-text">Loading…</p>}
          {docs?.length === 0 && (
            <p className="muted-text">No documents yet. Upload one, or run the seed command.</p>
          )}

          <ul className="doc-list">
            {docs?.map((d) => (
              <li key={d.id} className="doc-row">
                <DocIcon className="doc-row-icon" />
                <div className="doc-row-main">
                  <div className="doc-row-title">
                    <span className="doc-key">{d.doc_key}</span> {d.title}
                  </div>
                  <div className="doc-row-meta">
                    {[d.doc_type, d.owner, d.version && `v${d.version}`, `${d.chunk_count} passages`]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
                <span
                  className={`acl-pill ${d.acl.includes("all-employees") ? "" : "restricted"}`}
                  title={`Readable by: ${d.acl.join(", ")}`}
                >
                  {!d.acl.includes("all-employees") && <LockIcon width={12} height={12} />}
                  {d.acl.join(", ")}
                </span>
              </li>
            ))}
          </ul>
          <p className="muted-text small">
            You only see documents your groups can read. Restricted documents are filtered in the
            database, before anything reaches the model.
          </p>
        </div>
      </aside>
    </>
  );
}
