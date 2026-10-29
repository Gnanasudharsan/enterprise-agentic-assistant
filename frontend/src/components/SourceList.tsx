import { useState } from "react";

import type { RetrievalStatus, Source } from "../api";
import { BookIcon, ChevronIcon } from "./Icons";

interface Props {
  retrieval?: RetrievalStatus;
  sources: Source[];
  citations: number[];
  streaming: boolean;
  onOpen: (source: Source) => void;
}

export function RetrievalBadge({ retrieval, count }: { retrieval?: RetrievalStatus; count: number }) {
  if (!retrieval || retrieval === "disabled") return null;
  const text =
    retrieval === "used"
      ? `Searched company docs · ${count} passage${count === 1 ? "" : "s"}`
      : retrieval === "no_results"
        ? "No matching company documents"
        : "Knowledge base unavailable, answered without it";
  return (
    <div className={`retrieval-badge retrieval-${retrieval}`}>
      <BookIcon width={13} height={13} />
      {text}
    </div>
  );
}

function SourceCard({ source, onOpen }: { source: Source; onOpen: (s: Source) => void }) {
  const location = source.section.split(" › ").slice(1).join(" › ") || source.title;
  return (
    <button type="button" className="source-card" onClick={() => onOpen(source)}>
      <span className="source-num">{source.index}</span>
      <span className="source-text">
        <span className="source-title">
          <span className="doc-key">{source.doc_key}</span> {source.title}
        </span>
        <span className="source-loc">{location}</span>
      </span>
    </button>
  );
}

export function SourceList({ retrieval, sources, citations, streaming, onOpen }: Props) {
  const [showAll, setShowAll] = useState(false);
  if (streaming || retrieval !== "used" || sources.length === 0) return null;

  const cited = citations
    .map((n) => sources.find((s) => s.index === n))
    .filter((s): s is Source => Boolean(s));
  const others = sources.filter((s) => !citations.includes(s.index));

  return (
    <div className="sources">
      {cited.length > 0 && (
        <>
          <div className="sources-label">Sources</div>
          <div className="source-grid">
            {cited.map((s) => (
              <SourceCard key={s.chunk_id} source={s} onOpen={onOpen} />
            ))}
          </div>
        </>
      )}
      {cited.length === 0 && (
        <div className="sources-note">The answer does not cite any of the retrieved passages.</div>
      )}
      {others.length > 0 && (
        <>
          <button
            type="button"
            className={`text-button sources-toggle ${showAll ? "open" : ""}`}
            onClick={() => setShowAll((v) => !v)}
          >
            <ChevronIcon width={14} height={14} />
            {showAll ? "Hide" : "Show"} {others.length} other retrieved passage
            {others.length === 1 ? "" : "s"}
          </button>
          {showAll && (
            <div className="source-grid muted">
              {others.map((s) => (
                <SourceCard key={s.chunk_id} source={s} onOpen={onOpen} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
