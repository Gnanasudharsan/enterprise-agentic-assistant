// Typed client for the backend API. Shapes mirror backend/app/schemas/chat.py.

export type RetrievalStatus = "used" | "no_results" | "disabled" | "failed";

export interface Source {
  index: number;
  chunk_id: string;
  doc_key: string;
  title: string;
  section: string;
  snippet: string;
  source_path: string;
  doc_type: string | null;
  score: number;
}

export interface ChatResponse {
  run_id: string;
  answer: string;
  provider: string;
  model: string;
  latency_ms: number;
  usage: { prompt_tokens: number | null; completion_tokens: number | null };
  retrieval: RetrievalStatus;
  sources: Source[];
  citations: number[];
  invalid_citations: number;
}

export interface DocumentSummary {
  id: string;
  doc_key: string;
  title: string;
  doc_type: string | null;
  owner: string | null;
  version: string | null;
  source_updated: string | null;
  source_path: string;
  acl: string[];
  embedding_model: string;
  chunk_count: number;
  updated_at: string;
}

export interface ChunkDetail {
  chunk_id: string;
  chunk_index: number;
  section: string;
  content: string;
  token_count: number;
  document: DocumentSummary;
}

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AssistantInfo {
  version: string;
  provider: string;
  model: string;
  demo_mode: boolean;
  embedding_model: string;
  user_groups: string[];
}

export interface ReadyResponse {
  status: "ok" | "unavailable";
  database: "up" | "down";
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function parseError(resp: Response): Promise<ApiError> {
  let message = `Request failed (${resp.status})`;
  try {
    const body = await resp.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
  } catch {
    // Non-JSON error body; keep the generic message.
  }
  return new ApiError(resp.status, message);
}

export async function getInfo(): Promise<AssistantInfo> {
  const resp = await fetch("/api/v1/info");
  if (!resp.ok) throw await parseError(resp);
  return resp.json();
}

export async function checkReady(): Promise<ReadyResponse> {
  const resp = await fetch("/health/ready");
  return resp.json();
}

export async function listDocuments(): Promise<DocumentSummary[]> {
  const resp = await fetch("/api/v1/documents");
  if (!resp.ok) throw await parseError(resp);
  return (await resp.json()).documents;
}

export async function uploadDocument(
  file: File,
): Promise<{ status: "created" | "updated" | "unchanged"; document: DocumentSummary }> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/api/v1/documents", { method: "POST", body: form });
  if (!resp.ok) throw await parseError(resp);
  return resp.json();
}

export async function getChunk(chunkId: string): Promise<ChunkDetail> {
  const resp = await fetch(`/api/v1/chunks/${encodeURIComponent(chunkId)}`);
  if (!resp.ok) throw await parseError(resp);
  return resp.json();
}

/** Reads a Server-Sent Events response, calling onEvent for each event. */
async function readEvents(
  resp: Response,
  onEvent: (event: string, payload: any) => boolean | void,
): Promise<void> {
  if (!resp.ok || !resp.body) throw await parseError(resp);
  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;

    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (onEvent(event, JSON.parse(data)) === true) return; // finished
    }
  }
  throw new ApiError(502, "The connection closed before the answer finished.");
}

export interface StreamHandlers {
  onSources?: (retrieval: RetrievalStatus, sources: Source[]) => void;
  onDelta: (text: string) => void;
}

/**
 * Streams an answer over Server-Sent Events: `sources` first, then `delta` text
 * fragments. Resolves with the final, citation-checked response on `done`.
 */
export async function streamChat(
  prompt: string,
  history: HistoryMessage[],
  useKnowledgeBase: boolean,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const resp = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, history, use_knowledge_base: useKnowledgeBase }),
    signal,
  });
  let result: ChatResponse | undefined;
  await readEvents(resp, (event, payload) => {
    if (event === "sources") handlers.onSources?.(payload.retrieval, payload.sources);
    else if (event === "delta") handlers.onDelta(payload.text);
    else if (event === "error") throw new ApiError(payload.status, payload.detail);
    else if (event === "done") {
      result = payload;
      return true;
    }
  });
  return result!;
}

// ---------------------------------------------------------------- multi-agent runs
// Shapes mirror backend/app/schemas/agent.py.

export type AgentName = "research" | "data";

export interface PlanStep {
  id: string;
  agent: AgentName;
  goal: string;
  query: string;
  /** Research steps this step waits for (it then receives their findings). */
  depends_on?: string[];
}

export interface Plan {
  reasoning: string;
  steps: PlanStep[];
}

export interface Chart {
  type: "bar" | "line";
  x: string;
  y: string[];
  group: string | null;
}

export interface TableResult {
  index: number | null;
  step_id: string;
  title: string;
  question: string;
  sql: string | null;
  origin: "generated" | "certified" | null;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number | null;
  chart: Chart | null;
  error: string | null;
  attempts: { attempt: number; sql?: string | null; error: string }[];
}

export interface TraceEvent {
  node: string;
  status: string;
  started_at: string;
  duration_ms: number;
  summary: string;
  detail: Record<string, unknown>;
}

export interface AgentRun {
  run_id: string;
  status: "running" | "succeeded" | "failed";
  created_at: string | null;
  question: string;
  answer: string | null;
  provider: string;
  model: string | null;
  latency_ms: number | null;
  plan: Plan | null;
  sources: Source[];
  tables: TableResult[];
  citations: { sources: number[]; tables: number[] };
  invalid_citations: number;
  trace: TraceEvent[];
  error_type: string | null;
}

/** Live progress of one node or plan step, as streamed. */
export interface StepEvent {
  node: "supervisor" | "research" | "data" | "analyst";
  step_id?: string;
  status: "running" | "succeeded" | "fallback" | "failed";
  goal?: string;
  summary?: string;
  documents?: string[];
}

export interface SqlEvent {
  step_id: string;
  attempt: number;
  sql: string | null;
  status: "running" | "succeeded" | "failed";
  error?: string;
  rows?: number;
  origin?: "generated" | "certified";
}

export interface AgentHandlers {
  onRun?: (runId: string) => void;
  onPlan?: (plan: Plan, status: string) => void;
  onStep?: (step: StepEvent) => void;
  onSql?: (sql: SqlEvent) => void;
  onEvidence?: (sources: Source[], tables: TableResult[]) => void;
  onAnswerReset?: () => void;
  onDelta: (text: string) => void;
}

export class AgentRunError extends ApiError {
  constructor(
    status: number,
    message: string,
    public readonly runId: string | null,
  ) {
    super(status, message);
  }
}

async function driveAgent(resp: Response, handlers: AgentHandlers): Promise<AgentRun> {
  let result: AgentRun | undefined;
  await readEvents(resp, (event, p) => {
    switch (event) {
      case "run":
        handlers.onRun?.(p.run_id);
        break;
      case "plan":
        handlers.onPlan?.(p.plan, p.status);
        break;
      case "step":
        handlers.onStep?.(p);
        break;
      case "sql":
        handlers.onSql?.(p);
        break;
      case "evidence":
        handlers.onEvidence?.(p.sources.map((s: any) => ({ ...s, snippet: s.content?.slice(0, 600) ?? s.snippet })), p.tables);
        break;
      case "answer_reset":
        handlers.onAnswerReset?.();
        break;
      case "delta":
        handlers.onDelta(p.text);
        break;
      case "error":
        throw new AgentRunError(p.status, p.detail, p.run_id ?? null);
      case "done":
        result = p;
        return true;
    }
  });
  return result!;
}

/** Runs the multi-agent graph: plan, parallel research + data steps, then the answer. */
export async function streamAgent(
  prompt: string,
  history: HistoryMessage[],
  handlers: AgentHandlers,
  signal?: AbortSignal,
): Promise<AgentRun> {
  const resp = await fetch("/api/v1/agent/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, history }),
    signal,
  });
  return driveAgent(resp, handlers);
}

/** Continues a failed or interrupted run from its last checkpoint. */
export async function resumeAgent(
  runId: string,
  handlers: AgentHandlers,
  signal?: AbortSignal,
): Promise<AgentRun> {
  const resp = await fetch(`/api/v1/agent/runs/${encodeURIComponent(runId)}/resume`, {
    method: "POST",
    signal,
  });
  return driveAgent(resp, handlers);
}

export async function getAgentRun(runId: string): Promise<AgentRun> {
  const resp = await fetch(`/api/v1/agent/runs/${encodeURIComponent(runId)}`);
  if (!resp.ok) throw await parseError(resp);
  return resp.json();
}
