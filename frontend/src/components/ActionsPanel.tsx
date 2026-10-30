import { useEffect, useState } from "react";

import { type AgentAction, listActions } from "../api";
import { CloseIcon, TicketIcon } from "./Icons";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "proposed", label: "Pending" },
  { value: "executed", label: "Created" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
] as const;

export function ActionsPanel({ open, onClose, refreshKey }: { open: boolean; onClose: () => void; refreshKey: number }) {
  const [actions, setActions] = useState<AgentAction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["value"]>("all");

  useEffect(() => {
    if (!open) return;
    listActions()
      .then(setActions)
      .catch(() => setError("Couldn't load actions."));
  }, [open, refreshKey]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!open) return null;
  const shown = (actions ?? []).filter((a) => filter === "all" || a.status === filter);

  return (
    <>
      <div className="panel-scrim" onClick={onClose} />
      <aside className="panel panel-wide" role="dialog" aria-label="Actions and audit log">
        <header className="panel-head">
          <div>
            <div className="panel-kicker">Audit log</div>
            <h2 className="panel-title">Actions</h2>
            <p className="panel-sub">
              Every tool call an agent proposed, who decided, and what ran. Approval and
              permissions are enforced by the backend.
            </p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </header>
        <div className="panel-body">
          <div className="seg" role="radiogroup" aria-label="Filter" style={{ marginBottom: 14 }}>
            {FILTERS.map((f) => (
              <button key={f.value} type="button" role="radio" aria-checked={filter === f.value}
                className={filter === f.value ? "active" : ""} onClick={() => setFilter(f.value)}>
                {f.label}
              </button>
            ))}
          </div>
          {error && <p className="panel-error">{error}</p>}
          {actions && shown.length === 0 && <p className="history-empty">No actions here yet.</p>}
          <div className="audit-list">
            {shown.map((a) => (
              <div key={a.id} className={`audit-item action-${a.status}`}>
                <div className="audit-item-head">
                  <TicketIcon width={14} height={14} />
                  <span className="audit-item-title">{a.arguments.title}</span>
                  <span className={`run-status run-${a.status === "executed" ? "succeeded" : a.status === "failed" ? "failed" : "running"}`}>
                    {a.status}
                  </span>
                </div>
                <div className="audit-item-sub mono">
                  {a.tool} · {a.server}
                  {a.result?.key && ` · ${a.result.key}`} · run {a.run_id.slice(0, 8)}
                </div>
                {a.error && <div className="action-error">{a.error}</div>}
                <ol className="audit-line">
                  {a.audit.map((e, i) => (
                    <li key={i} className={`audit-${e.event}`}>
                      <span className="audit-dot" />
                      {e.event}
                      <span className="audit-actor">{e.actor === "system" ? "backend" : e.actor}</span>
                      <span className="audit-time mono">{e.at ? new Date(e.at).toLocaleString() : ""}</span>
                      {e.detail?.reason && <span className="audit-reason">{e.detail.reason}</span>}
                      {e.detail?.fields && <span className="audit-reason">changed {e.detail.fields.join(", ")}</span>}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  );
}
