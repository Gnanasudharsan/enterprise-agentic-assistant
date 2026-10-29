import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ApiError, type ChunkDetail, getChunk, type Source } from "../api";
import { CloseIcon, LockIcon } from "./Icons";

interface Props {
  source: Source | null;
  onClose: () => void;
}

export function SourcePanel({ source, onClose }: Props) {
  const [detail, setDetail] = useState<ChunkDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!source) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    getChunk(source.chunk_id)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => {
        if (cancelled) return;
        setError(
          e instanceof ApiError && e.status === 404
            ? "This passage is no longer available (it may have been re-ingested)."
            : "Couldn't load the passage.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!source) return null;
  const doc = detail?.document;

  return (
    <>
      <div className="panel-scrim" onClick={onClose} />
      <aside className="panel" aria-label="Source passage">
        <header className="panel-head">
          <div>
            <div className="panel-kicker">
              Source {source.index} · <span className="doc-key">{source.doc_key}</span>
            </div>
            <h2 className="panel-title">{source.title}</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="panel-body">
          <div className="breadcrumb">{source.section}</div>
          <div className="passage markdown">
            <Markdown remarkPlugins={[remarkGfm]}>{detail?.content ?? source.snippet}</Markdown>
          </div>
          {error && <p className="panel-error">{error}</p>}

          {doc && (
            <dl className="doc-meta">
              <div>
                <dt>Type</dt>
                <dd>{doc.doc_type ?? "—"}</dd>
              </div>
              <div>
                <dt>Owner</dt>
                <dd>{doc.owner ?? "—"}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>
                  {doc.version ?? "—"}
                  {doc.source_updated && ` · updated ${doc.source_updated}`}
                </dd>
              </div>
              <div>
                <dt>Access</dt>
                <dd className="acl">
                  <LockIcon width={13} height={13} />
                  {doc.acl.join(", ")}
                </dd>
              </div>
              <div>
                <dt>File</dt>
                <dd className="mono">{doc.source_path}</dd>
              </div>
              <div>
                <dt>Passage</dt>
                <dd>
                  #{(detail?.chunk_index ?? 0) + 1} of {doc.chunk_count} · relevance{" "}
                  {source.score.toFixed(3)}
                </dd>
              </div>
            </dl>
          )}
        </div>
      </aside>
    </>
  );
}
