// Conversations are kept in this browser only (a per-viewer convenience). Agent runs
// are also recorded server-side, with their full trace (GET /api/v1/agent/runs/{id}).

import type {
  ChatResponse,
  Plan,
  RetrievalStatus,
  Source,
  SqlEvent,
  StepEvent,
  TableResult,
  TraceEvent,
} from "./api";

/** agent: plan + documents + data. docs: grounded chat. general: no company data. */
export type Mode = "agent" | "docs" | "general";

/** What the agents did for one answer: streamed live, then replaced by the final run. */
export interface AgentProgress {
  runId?: string;
  plan?: Plan;
  planStatus?: string;
  /** Latest event per node ("supervisor", "analyst") or plan step id ("s1"). */
  steps: Record<string, StepEvent>;
  /** Latest SQL event per data step. */
  sql: Record<string, SqlEvent>;
  tables?: TableResult[];
  tableCitations?: number[];
  trace?: TraceEvent[];
  latencyMs?: number;
  model?: string | null;
  invalidCitations?: number;
  /** The run failed after checkpointing; it can be resumed. */
  resumable?: boolean;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "done" | "error" | "stopped";
  error?: string;
  /** Whether this answer was asked with company documents on (assistant messages). */
  kb?: boolean;
  mode?: Mode;
  agent?: AgentProgress;
  retrieval?: RetrievalStatus;
  sources?: Source[];
  citations?: number[];
  meta?: Omit<ChatResponse, "answer" | "sources" | "citations" | "retrieval">;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
}

const KEY = "eaa.conversations.v1";
const MAX_CONVERSATIONS = 30;

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as Conversation[]) : [];
    // A reload mid-stream leaves half-finished answers; mark them as stopped.
    return parsed.map((c) => ({
      ...c,
      messages: c.messages.map((m) =>
        m.status === "streaming" ? { ...m, status: "stopped" as const } : m,
      ),
    }));
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[]): void {
  try {
    const kept = conversations
      .filter((c) => c.messages.length > 0)
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CONVERSATIONS);
    localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {
    // Storage unavailable (private mode, quota); the app still works in memory.
  }
}

export function newId(): string {
  return crypto.randomUUID();
}

export function titleFrom(prompt: string): string {
  const oneLine = prompt.replace(/\s+/g, " ").trim();
  return oneLine.length > 48 ? `${oneLine.slice(0, 45)}…` : oneLine;
}
