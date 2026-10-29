// Typed client for the backend API. Shapes mirror backend/app/schemas/chat.py.

export interface ChatResponse {
  run_id: string;
  answer: string;
  provider: string;
  model: string;
  latency_ms: number;
  usage: { prompt_tokens: number | null; completion_tokens: number | null };
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

/**
 * Streams an answer over Server-Sent Events. Calls `onDelta` for each text fragment
 * and resolves with the final response once the server sends `done`.
 */
export async function streamChat(
  prompt: string,
  history: HistoryMessage[],
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const resp = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, history }),
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
      if (event === "delta") onDelta(payload.text);
      else if (event === "done") return payload as ChatResponse;
      else if (event === "error") throw new ApiError(payload.status, payload.detail);
    }
  }
  throw new ApiError(502, "The connection closed before the answer finished.");
}
