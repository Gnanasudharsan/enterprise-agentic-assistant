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
      const payload = JSON.parse(data);
      if (event === "sources") handlers.onSources?.(payload.retrieval, payload.sources);
      else if (event === "delta") handlers.onDelta(payload.text);
      else if (event === "done") return payload as ChatResponse;
      else if (event === "error") throw new ApiError(payload.status, payload.detail);
    }
  }
  throw new ApiError(502, "The connection closed before the answer finished.");
}
