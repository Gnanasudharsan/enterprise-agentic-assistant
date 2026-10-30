import { useEffect, useState } from "react";

import { type AgentRun, getAgentRun, type TraceEvent } from "../api";
import { BookIcon, CloseIcon, DatabaseIcon, PenIcon, RouteIcon } from "./Icons";

const NODE = {
  supervisor: { label: "Supervisor", icon: RouteIcon },
  research: { label: "Docs agent", icon: BookIcon },
  data: { label: "Data agent", icon: DatabaseIcon },
  analyst: { label: "Analyst", icon: PenIcon },
} as const;

function Detail({ event }: { event: TraceEvent }) {
  const d = event.detail as Record<string, any>;
  const items: [string, React.ReactNode][] = [];
  if (d.reasoning) items.push(["Reasoning", d.reasoning]);
  if (d.query) items.push(["Search query", d.query]);
  if (d.question) items.push(["Question", d.question]);
  if (d.documents?.length) items.push(["Documents", d.documents.join(", ")]);
  if (d.attempts !== undefined) items.push(["Attempts", String(d.attempts)]);
  if (d.problems?.length) items.push(["Problems", d.problems.join("; ")]);
  if (d.adjustments?.length) items.push(["Plan rules applied", d.adjustments.join("; ")]);
  if (d.used_findings) items.push(["Used findings", "Yes, from the docs agent"]);
  if (d.invalid_citations !== undefined) items.push(["Invalid citations removed", String(d.invalid_citations)]);
  if (d.prompt_tokens) items.push(["Tokens", `${d.prompt_tokens} in → ${d.completion_tokens} out`]);
  return (
    <>
      {items.length > 0 && (
        <dl className="trace-detail">
          {items.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {d.sql && (
        <pre className="trace-sql">
          <code>{d.sql}</code>
        </pre>
      )}
    </>
  );
}

export function TracePanel({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setRun(null);
    setError(null);
    setExpanded(null);
    getAgentRun(runId)
      .then((r) => !cancelled && setRun(r))
      .catch(() => !cancelled && setError("Couldn't load this run's trace."));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!runId) return null;

  const trace = run?.trace ?? [];
  const t0 = Math.min(...trace.map((e) => Date.parse(e.started_at)));
  const end = Math.max(...trace.map((e) => Date.parse(e.started_at) + e.duration_ms));
  const span = Math.max(1, end - t0);

  return (
    <>
      <div className="panel-scrim" onClick={onClose} />
      <aside className="panel panel-wide" role="dialog" aria-label="Run trace">
        <header className="panel-head">
          <div>
            <div className="panel-kicker">
              Execution trace
              {run && <span className={`run-status run-${run.status}`}>{run.status}</span>}
            </div>
            <h2 className="panel-title">{run?.question ?? "Loading…"}</h2>
            {run && (
              <p className="panel-sub mono">
                {run.run_id.slice(0, 8)} · {run.model} · {((run.latency_ms ?? 0) / 1000).toFixed(1)}s
              </p>
            )}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="panel-body">
          {error && <p className="panel-error">{error}</p>}
          {run?.plan && (
            <section className="trace-section">
              <h3>Plan</h3>
              {run.plan.reasoning && <p className="trace-reasoning">{run.plan.reasoning}</p>}
              <ol className="trace-plan">
                {run.plan.steps.map((s) => (
                  <li key={s.id}>
                    <span className="mono">{s.id}</span>
                    <span className="agent-tag">{s.agent === "data" ? "Data agent" : "Docs agent"}</span>
                    <span>{s.goal}</span>
                    {s.depends_on?.length ? (
                      <span className="trace-after mono">after {s.depends_on.join(", ")}</span>
                    ) : null}
                  </li>
                ))}
                {run.plan.steps.length === 0 && <li>No specialist steps; answered directly.</li>}
              </ol>
            </section>
          )}

          {trace.length > 0 && (
            <section className="trace-section">
              <h3>Timeline</h3>
              <div className="waterfall">
                {trace.map((e, i) => {
                  const meta = NODE[e.node as keyof typeof NODE] ?? { label: e.node, icon: RouteIcon };
                  const Icon = meta.icon;
                  const left = ((Date.parse(e.started_at) - t0) / span) * 100;
                  const width = Math.max(0.8, (e.duration_ms / span) * 100);
                  const stepId = (e.detail as { step_id?: string }).step_id;
                  return (
                    <div key={i} className={`wf-row wf-${e.status}`}>
                      <button
                        type="button"
                        className="wf-head"
                        onClick={() => setExpanded(expanded === i ? null : i)}
                        aria-expanded={expanded === i}
                      >
                        <span className="wf-name">
                          <Icon width={13} height={13} />
                          {meta.label}
                          {stepId && <span className="mono wf-step">{stepId}</span>}
                        </span>
                        <span className="wf-track">
                          <span className="wf-bar" style={{ left: `${left}%`, width: `${width}%` }} />
                        </span>
                        <span className="wf-ms mono">{e.duration_ms.toLocaleString()} ms</span>
                      </button>
                      <div className="wf-summary">
                        {e.status !== "succeeded" && <span className={`wf-badge wf-badge-${e.status}`}>{e.status}</span>}
                        {e.summary}
                      </div>
                      {expanded === i && <Detail event={e} />}
                    </div>
                  );
                })}
              </div>
              <p className="trace-note">
                Steps that overlap ran in parallel. Each step is checkpointed in Postgres, so a
                failed run resumes from the last completed step.
              </p>
            </section>
          )}
        </div>
      </aside>
    </>
  );
}
