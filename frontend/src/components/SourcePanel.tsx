import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { untrustedComponents } from "./markdown";

import { ApiError, type ChunkDetail, getChunk, type Source } from "../api";
import { docType } from "../docTypes";
import { CloseIcon, LockIcon } from "./Icons";

interface Props {
  source: Source | null;
  total: number;
  onClose: () => void;
}

export function SourcePanel({ source, total, onClose }: Props) {
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
            ? "This passage is no longer available (the document may have been re-ingested). Showing the stored excerpt."
            : "Couldn't load the full passage. Showing the stored excerpt.",
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
  const t = docType(source.doc_type);
  const crumbs = source.section.split(" › ");

  return (
    <>
      <div className="panel-scrim" onClick={onClose} />
      <aside className="panel" role="dialog" aria-label={`Source ${source.index}`}>
        <header className="panel-head">
          <div>
            <div className="panel-kicker">
              Source {source.index}
              <span className={`type-badge tone-${t.tone}`}>
                <span className="type-dot" />
                {t.label}
              </span>
              <span className="mono">{source.doc_key}</span>
            </div>
            <h2 className="panel-title">{source.title}</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="panel-body">
          <div className="breadcrumb">
            {crumbs.map((c, i) => (
              <span key={i}>{c}</span>
            ))}
          </div>
          <div className="passage markdown">
            <Markdown remarkPlugins={[remarkGfm]} components={untrustedComponents}>{detail?.content ?? source.snippet}</Markdown>
          </div>
          {error && <p className="panel-error">{error}</p>}

          <dl className="doc-meta">
            <div>
              <dt>Owner</dt>
              <dd>{doc?.owner ?? "—"}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>
                {doc?.version ? `v${doc.version}` : "—"}
                {doc?.source_updated && ` · ${doc.source_updated}`}
              </dd>
            </div>
            <div>
              <dt>Access</dt>
              <dd className="acl">
                <LockIcon width={13} height={13} />
                {doc?.acl.join(", ") ?? "—"}
              </dd>
            </div>
            <div>
              <dt>Retrieval rank</dt>
              <dd>
                #{source.index} of {total} passages
              </dd>
            </div>
            <div>
              <dt>Passage</dt>
              <dd>
                {detail ? `${detail.chunk_index + 1} of ${doc?.chunk_count} · ~${detail.token_count} tokens` : "—"}
              </dd>
            </div>
            <div>
              <dt>File</dt>
              <dd className="mono">{doc?.source_path ?? source.source_path}</dd>
            </div>
          </dl>
        </div>
      </aside>
    </>
  );
}
