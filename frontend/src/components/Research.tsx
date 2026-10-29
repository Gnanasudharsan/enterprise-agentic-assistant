import { useRef, useState } from "react";

import type { Source } from "../api";
import { docType, sectionLabel } from "../docTypes";
import type { Message } from "../storage";
import { CheckIcon, ChevronIcon } from "./Icons";

type StepState = "pending" | "active" | "done" | "warn";

interface Step {
  state: StepState;
  label: string;
  detail?: string;
}

function steps(message: Message): Step[] {
  const kb = message.kb !== false;
  const sources = message.sources ?? [];
  const docs = new Set(sources.map((s) => s.doc_key)).size;
  const searching = kb && message.retrieval === undefined && message.status === "streaming";
  const result: Step[] = [];

  if (kb) {
    if (searching) result.push({ state: "active", label: "Searching the knowledge base" });
    else if (message.retrieval === "used")
      result.push({
        state: "done",
        label: "Searched the knowledge base",
        detail: `${sources.length} passages from ${docs} document${docs === 1 ? "" : "s"}, vector + keyword`,
      });
    else if (message.retrieval === "no_results")
      result.push({ state: "warn", label: "No matching documents", detail: "Answering from general knowledge" });
    else if (message.retrieval === "failed")
      result.push({ state: "warn", label: "Knowledge base unavailable", detail: "Answering without it" });
  }

  const writing: Step = { state: "pending", label: "Writing the answer" };
  if (message.status === "streaming" && !searching) writing.state = "active";
  if (message.status === "done") {
    writing.state = "done";
    writing.label = "Answer ready";
    const cited = message.citations?.length ?? 0;
    writing.detail = kb && sources.length ? `${cited} source${cited === 1 ? "" : "s"} cited, all verified` : undefined;
  }
  if (message.status === "error" || message.status === "stopped") {
    writing.state = "warn";
    writing.label = message.status === "error" ? "Answer failed" : "Stopped";
  }
  result.push(writing);
  return result;
}

export function ResearchSteps({ message }: { message: Message }) {
  const [open, setOpen] = useState(false);
  const list = steps(message);
  const finished = message.status !== "streaming";

  const stepList = (
    <ol className="steps-list">
      {list.map((s) => (
        <li key={s.label} className={`step ${s.state}`}>
          <span className="step-icon">
            {s.state === "done" && <CheckIcon width={10} height={10} strokeWidth={3} />}
            {s.state === "warn" && <span style={{ fontSize: 10, fontWeight: 700 }}>!</span>}
          </span>
          <span>
            <span className={s.state === "active" ? "shimmer" : undefined}>{s.label}</span>
            {s.detail && <span className="step-detail">{s.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  );

  if (!finished) return <div className="steps">{stepList}</div>;

  const sources = message.sources ?? [];
  const seconds = message.meta ? ` · ${(message.meta.latency_ms / 1000).toFixed(1)}s` : "";
  const summary =
    message.retrieval === "used"
      ? `Researched ${sources.length} passages${seconds}`
      : message.kb === false
        ? `General answer, no company documents${seconds}`
        : `Answered without matching documents${seconds}`;

  return (
    <div className="steps">
      <button
        type="button"
        className={`steps-summary ${open ? "open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="steps-check">
          <CheckIcon width={10} height={10} strokeWidth={3} />
        </span>
        {summary}
        <ChevronIcon className="chev" width={14} height={14} />
      </button>
      {open && stepList}
    </div>
  );
}

export function SourceStrip({
  sources,
  citations,
  settled,
  onOpen,
}: {
  sources: Source[];
  citations: number[];
  settled: boolean;
  onOpen: (s: Source) => void;
}) {
  if (sources.length === 0) return null;
  // Once the answer is final, cited sources come first and the rest fade back.
  const ordered = settled
    ? [...sources].sort((a, b) => Number(citations.includes(b.index)) - Number(citations.includes(a.index)))
    : sources;

  return (
    <div className="source-strip" role="list" aria-label="Sources">
      {ordered.map((s, i) => {
        const t = docType(s.doc_type);
        const cited = citations.includes(s.index);
        return (
          <button
            key={s.chunk_id}
            type="button"
            role="listitem"
            className={`source-card tone-${t.tone} ${settled ? (cited ? "cited" : "uncited") : ""}`}
            style={{ animationDelay: `${i * 40}ms` }}
            onClick={() => onOpen(s)}
            title={`${s.doc_key} · ${s.section}`}
          >
            <span className="sc-top">
              <span className="sc-index">{s.index}</span>
              <span className="type-dot" />
              <span className="sc-key">{s.doc_key}</span>
              <span>· {t.label}</span>
            </span>
            <span className="sc-title">{s.title}</span>
            <span className="sc-loc">{sectionLabel(s.section, s.title)}</span>
          </button>
        );
      })}
    </div>
  );
}

export function CitationChip({
  n,
  source,
  onOpen,
}: {
  n: number;
  source: Source | undefined;
  onOpen: (s: Source) => void;
}) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const show = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), 120);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    setOpen(false);
  };
  const t = docType(source?.doc_type);

  return (
    <span className={`cite-wrap ${open ? "open" : ""}`} onMouseEnter={show} onMouseLeave={hide}>
      <button
        type="button"
        className="cite"
        onFocus={show}
        onBlur={hide}
        onClick={() => source && onOpen(source)}
        aria-label={source ? `Source ${n}: ${source.title}, ${source.section}` : `Source ${n}`}
      >
        {n}
      </button>
      {open && source && (
        <span className={`cite-card tone-${t.tone}`} role="tooltip">
          <span className="cite-card-top">
            <span className="type-dot" />
            <span className="mono">{source.doc_key}</span> · {t.label}
          </span>
          <span className="cite-card-title" style={{ display: "block" }}>
            {source.title}
          </span>
          <span className="cite-card-loc" style={{ display: "block" }}>
            {sectionLabel(source.section, source.title)}
          </span>
          <span className="cite-card-snippet">{source.snippet.replace(/\*\*/g, "")}</span>
          <span className="cite-card-hint" style={{ display: "block" }}>
            Click to open the full passage
          </span>
        </span>
      )}
    </span>
  );
}
