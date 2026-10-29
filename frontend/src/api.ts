// Typed client for the backend API. Shapes mirror backend/app/schemas/chat.py.

export interface ChatResponse {
  run_id: string;
  answer: string;
  provider: string;
  model: string;
  latency_ms: number;
  usage: { prompt_tokens: number | null; completion_tokens: number | null };
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

export async function sendChat(prompt: string, signal?: AbortSignal): Promise<ChatResponse> {
  const resp = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal,
  });
  if (!resp.ok) throw await parseError(resp);
  return resp.json();
}

export async function checkReady(): Promise<ReadyResponse> {
  const resp = await fetch("/health/ready");
  return resp.json();
}
