import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { AgentAction, IssueArguments, ToolInfo } from "../api";
import { CheckIcon, CloseIcon, PenIcon, ShieldIcon, TicketIcon } from "./Icons";

interface Props {
  action: AgentAction;
  tool: ToolInfo | undefined;
  busy: boolean;
  onDecide: (decision: "approve" | "reject", args?: IssueArguments) => void;
}

const STATUS: Record<AgentAction["status"], { label: string; tone: string }> = {
  proposed: { label: "Needs your approval", tone: "warn" },
  approved: { label: "Approved", tone: "info" },
  executing: { label: "Creating…", tone: "info" },
  executed: { label: "Created", tone: "ok" },
  rejected: { label: "Rejected", tone: "muted" },
  failed: { label: "Failed", tone: "bad" },
};

const EVENT_LABEL: Record<string, string> = {
  proposed: "Proposed",
  edited: "Edited",
  approved: "Approved",
  rejected: "Rejected",
  denied: "Blocked",
  executing: "Sent to tracker",
  executed: "Created",
  failed: "Failed",
};

function enumOf(tool: ToolInfo | undefined, field: string, fallback: string[]): string[] {
  const prop = tool?.input_schema.properties?.[field];
  return prop?.items?.enum ?? prop?.enum ?? fallback;
}

function time(at: string | null): string {
  return at ? new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
}

export function ActionCard({ action, tool, busy, onDecide }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<IssueArguments>(action.arguments);
  const [expanded, setExpanded] = useState(false);
  const status = STATUS[action.status];
  const args = action.arguments;
  const labelsAll = enumOf(tool, "labels", ["onboarding", "verification", "support", "incident-follow-up", "bug", "docs"]);
  const priorities = enumOf(tool, "priority", ["P1", "P2", "P3", "P4"]);
  const duplicates: { key: string; title: string }[] =
    action.audit.find((e) => e.event === "proposed")?.detail?.duplicates ?? [];
  const pending = action.status === "proposed";
  const link = action.result?.url?.startsWith("http") ? action.result.url : null;

  return (
    <div className={`action-card action-${action.status}`}>
      <div className="action-head">
        <span className="action-icon">
          <TicketIcon width={16} height={16} />
        </span>
        <div className="action-head-text">
          <div className="action-kicker">
            Proposed action · <span className="mono">{action.tool}</span> · {action.server}
          </div>
          {!editing && <div className="action-title">{args.title}</div>}
        </div>
        <span className={`action-status tone-${status.tone}`}>{status.label}</span>
      </div>

      {editing ? (
        <div className="action-edit">
          <label>
            <span>Title</span>
            <input
              value={draft.title}
              maxLength={120}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </label>
          <div className="action-edit-row">
            <label>
              <span>Priority</span>
              <select
                value={draft.priority ?? "P3"}
                onChange={(e) => setDraft({ ...draft, priority: e.target.value })}
              >
                {priorities.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
            <div className="action-label-picker">
              <span>Labels</span>
              <div>
                {labelsAll.map((l) => {
                  const on = draft.labels?.includes(l) ?? false;
                  return (
                    <button
                      type="button"
                      key={l}
                      className={`chip ${on ? "on" : ""}`}
                      aria-pressed={on}
                      onClick={() =>
                        setDraft({
                          ...draft,
                          labels: on ? draft.labels?.filter((x) => x !== l) : [...(draft.labels ?? []), l],
                        })
                      }
                    >
                      {l}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          <label>
            <span>Description (Markdown)</span>
            <textarea
              value={draft.body}
              rows={10}
              maxLength={6000}
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
            />
          </label>
        </div>
      ) : (
        <>
          <div className="action-meta">
            {args.priority && <span className={`chip prio prio-${args.priority}`}>{args.priority}</span>}
            {args.labels?.map((l) => (
              <span key={l} className="chip">
                {l}
              </span>
            ))}
          </div>
          <div className={`action-body markdown ${expanded ? "expanded" : ""}`}>
            <Markdown remarkPlugins={[remarkGfm]}>{args.body}</Markdown>
          </div>
          {args.body.length > 400 && (
            <button type="button" className="text-button" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Show less" : "Show full description"}
            </button>
          )}
          {action.rationale && <p className="action-rationale">Why: {action.rationale}</p>}
          {pending && duplicates.length > 0 && (
            <div className="action-dupes">
              Possible duplicates:{" "}
              {duplicates.map((d) => (
                <span key={d.key} className="mono">
                  {d.key} {d.title}
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {pending && (
        <div className="action-footer">
          <p className="action-policy">
            <ShieldIcon width={13} height={13} /> Nothing is created until you approve. The backend
            re-checks your permission and the exact contents before running it.
          </p>
          <div className="action-buttons">
            {editing ? (
              <>
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => {
                  setDraft(action.arguments);
                  setEditing(false);
                }}>
                  Cancel
                </button>
                <button type="button" className="btn btn-primary" disabled={busy || draft.title.trim().length < 8}
                  onClick={() => onDecide("approve", draft)}>
                  <CheckIcon width={14} height={14} /> Approve edited issue
                </button>
              </>
            ) : (
              <>
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => onDecide("reject")}>
                  <CloseIcon width={14} height={14} /> Reject
                </button>
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setEditing(true)}>
                  <PenIcon width={14} height={14} /> Edit
                </button>
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onDecide("approve")}>
                  <CheckIcon width={14} height={14} /> Approve &amp; create
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {!pending && (
        <div className="action-outcome">
          {action.status === "executed" && action.result?.key && (
            <div className="action-created">
              <CheckIcon width={14} height={14} /> Created{" "}
              {link ? (
                <a href={link} target="_blank" rel="noreferrer" className="mono">
                  {action.result.key}
                </a>
              ) : (
                <span className="mono">{action.result.key}</span>
              )}
            </div>
          )}
          {action.error && <div className="action-error">{action.error}</div>}
          <ol className="audit-line" aria-label="Audit trail">
            {action.audit.map((e, i) => (
              <li key={i} className={`audit-${e.event}`}>
                <span className="audit-dot" />
                {EVENT_LABEL[e.event] ?? e.event}
                <span className="audit-actor">{e.actor === "system" ? "backend" : e.actor}</span>
                <span className="audit-time mono">{time(e.at)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
