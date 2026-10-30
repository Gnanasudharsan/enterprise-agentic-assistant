import { type ReactNode, useState } from "react";

import type { PlanStep, StepEvent } from "../api";
import type { AgentProgress, Message } from "../storage";
import {
  ActivityIcon,
  BookIcon,
  CheckIcon,
  ChevronIcon,
  DatabaseIcon,
  PenIcon,
  RouteIcon,
} from "./Icons";

type RowState = "pending" | "active" | "done" | "warn" | "bad";

interface Row {
  key: string;
  state: RowState;
  icon: ReactNode;
  agent: string;
  label: string;
  detail?: ReactNode;
}

const AGENT_LABEL = { research: "Docs agent", data: "Data agent" } as const;

function stateOf(e: StepEvent | undefined, streaming: boolean): RowState {
  if (!e) return streaming ? "pending" : "warn";
  if (e.status === "running") return streaming ? "active" : "warn";
  if (e.status === "failed") return "bad";
  if (e.status === "fallback") return "warn";
  return "done";
}

function stepRow(step: PlanStep, agent: AgentProgress, streaming: boolean): Row {
  const e = agent.steps[step.id];
  const sql = agent.sql[step.id];
  const table = agent.tables?.find((t) => t.step_id === step.id);
  const waits = step.depends_on ?? [];
  let detail: ReactNode =
    e?.summary ??
    (e?.status === "running"
      ? waits.length
        ? `Using findings from ${waits.join(", ")}`
        : undefined
      : !e && waits.length && streaming
        ? `Waits for ${waits.join(", ")} to finish`
        : step.query);

  if (step.agent === "data") {
    const repaired = table?.attempts.length ?? 0;
    const notes: string[] = [];
    if (e?.status === "running" && sql?.status === "running") notes.push("Running SQL…");
    if (e?.status === "running" && sql?.status === "failed") notes.push(`Query rejected, repairing (attempt ${sql.attempt + 1})`);
    if (table?.origin === "certified") notes.push("used a reviewed query");
    else if (repaired) notes.push(`self-corrected after ${repaired} failed ${repaired === 1 ? "query" : "queries"}`);
    if (waits.length && e && e.status !== "running") notes.push(`used findings from ${waits.join(", ")}`);
    if (notes.length) detail = [e?.summary, ...notes].filter(Boolean).join(" · ");
  }
  return {
    key: step.id,
    state: stateOf(e, streaming),
    icon: step.agent === "data" ? <DatabaseIcon width={12} height={12} /> : <BookIcon width={12} height={12} />,
    agent: AGENT_LABEL[step.agent],
    label: step.goal,
    detail,
  };
}

function rows(message: Message): Row[] {
  const agent = message.agent!;
  const streaming = message.status === "streaming";
  const sup = agent.steps.supervisor;
  const result: Row[] = [];

  const planned = agent.plan;
  result.push({
    key: "supervisor",
    state: planned ? (agent.planStatus === "fallback" ? "warn" : "done") : streaming ? "active" : "warn",
    icon: <RouteIcon width={12} height={12} />,
    agent: "Supervisor",
    label: !planned
      ? "Planning the research"
      : planned.steps.length === 0
        ? "No lookup needed"
        : `Planned ${planned.steps.length} step${planned.steps.length === 1 ? "" : "s"}${
            planned.steps.length < 2 ? "" : planned.steps.some((s) => s.depends_on?.length) ? " in two waves" : ", running in parallel"
          }`,
    detail:
      agent.planStatus === "fallback"
        ? "Model unavailable, used a keyword plan"
        : planned?.reasoning || (sup?.status === "running" ? undefined : undefined),
  });

  for (const step of planned?.steps ?? []) result.push(stepRow(step, agent, streaming));

  if (planned) {
    const analyst = agent.steps.analyst;
    const done = message.status === "done";
    const sources = message.citations?.length ?? 0;
    const tables = agent.tableCitations?.length ?? 0;
    result.push({
      key: "analyst",
      state: done ? "done" : message.status === "streaming" ? (analyst ? "active" : "pending") : "bad",
      icon: <PenIcon width={12} height={12} />,
      agent: "Analyst",
      label: done ? "Answer written" : message.status === "streaming" ? "Writing the answer" : message.status === "stopped" ? "Stopped" : "Answer failed",
      detail: done
        ? `Cites ${sources} source${sources === 1 ? "" : "s"} and ${tables} table${tables === 1 ? "" : "s"}, all verified`
        : undefined,
    });
  }
  return result;
}

function Timeline({ list }: { list: Row[] }) {
  return (
    <ol className="steps-list agent-steps">
      {list.map((r) => (
        <li key={r.key} className={`step ${r.state === "bad" ? "warn bad" : r.state}`}>
          <span className="step-icon">
            {r.state === "done" && <CheckIcon width={10} height={10} strokeWidth={3} />}
            {(r.state === "warn" || r.state === "bad") && <span style={{ fontSize: 10, fontWeight: 700 }}>!</span>}
          </span>
          <span className="agent-step-body">
            <span className="agent-tag">
              {r.icon}
              {r.agent}
            </span>
            <span className={r.state === "active" ? "shimmer" : undefined}>{r.label}</span>
            {r.detail && <span className="step-detail">{r.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function AgentSteps({ message, onOpenTrace }: { message: Message; onOpenTrace: () => void }) {
  const [open, setOpen] = useState(false);
  const agent = message.agent;
  if (!agent) return null;
  const list = rows(message);
  if (message.status === "streaming") return <div className="steps">{<Timeline list={list} />}</div>;

  const steps = agent.plan?.steps ?? [];
  const passages = message.sources?.length ?? 0;
  const queries = agent.tables?.filter((t) => !t.error).length ?? 0;
  const parts = [
    steps.length ? `Ran ${new Set(steps.map((s) => s.agent)).size + 2} agents` : "Answered directly",
    passages ? `${passages} passages` : null,
    queries ? `${queries} ${queries === 1 ? "query" : "queries"}` : null,
    agent.latencyMs ? `${(agent.latencyMs / 1000).toFixed(1)}s` : null,
  ].filter(Boolean);
  const problems = list.some((r) => r.state === "warn" || r.state === "bad");

  return (
    <div className="steps">
      <div className="steps-row">
        <button
          type="button"
          className={`steps-summary ${open ? "open" : ""}`}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <span className={`steps-check ${problems ? "warn" : ""}`}>
            {problems ? <span style={{ fontSize: 10, fontWeight: 700 }}>!</span> : <CheckIcon width={10} height={10} strokeWidth={3} />}
          </span>
          {parts.join(" · ")}
          <ChevronIcon className="chev" width={14} height={14} />
        </button>
        {agent.runId && (
          <button type="button" className="trace-link" onClick={onOpenTrace}>
            <ActivityIcon width={13} height={13} /> Trace
          </button>
        )}
      </div>
      {open && <Timeline list={list} />}
    </div>
  );
}
