import { type FormEvent, useEffect, useState } from "react";

import { ApiError, type ChatResponse, checkReady, sendChat } from "./api";

type Backend = "checking" | "ready" | "degraded" | "offline";

interface Turn {
  prompt: string;
  response?: ChatResponse;
  error?: string;
}

const EXAMPLES = [
  "What should a new employee do in their first week?",
  "Summarize the risks of slow customer onboarding.",
];

export default function App() {
  const [backend, setBackend] = useState<Backend>("checking");
  const [prompt, setPrompt] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    checkReady()
      .then((r) => setBackend(r.status === "ok" ? "ready" : "degraded"))
      .catch(() => setBackend("offline"));
  }, []);

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = prompt.trim();
    if (!text || loading) return;

    setLoading(true);
    setPrompt("");
    setTurns((t) => [{ prompt: text }, ...t]);
    try {
      const response = await sendChat(text);
      setTurns((t) => [{ prompt: text, response }, ...t.slice(1)]);
    } catch (err) {
      const error = err instanceof ApiError ? err.message : "Could not reach the backend.";
      setTurns((t) => [{ prompt: text, error }, ...t.slice(1)]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Enterprise Agentic Assistant</h1>
          <p className="subtitle">Phase 1 · single-turn Q&amp;A through the FastAPI backend</p>
        </div>
        <span className={`pill pill-${backend}`}>
          <span className="dot" /> backend {backend}
        </span>
      </header>

      <form className="composer" onSubmit={submit}>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder="Ask a business question… (Enter to send, Shift+Enter for a new line)"
          rows={3}
          maxLength={8000}
          aria-label="Prompt"
        />
        <div className="composer-row">
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button type="button" key={ex} className="chip" onClick={() => setPrompt(ex)}>
                {ex}
              </button>
            ))}
          </div>
          <button type="submit" className="send" disabled={loading || !prompt.trim()}>
            {loading ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>

      <main className="turns">
        {turns.length === 0 && (
          <p className="empty">
            Answers appear here with their provider, model, latency, and run ID. Document
            retrieval and citations arrive in Phase 2.
          </p>
        )}
        {turns.map((turn, i) => (
          <article key={turns.length - i} className="turn">
            <p className="question">{turn.prompt}</p>
            {!turn.response && !turn.error && <p className="pending">Waiting for the model…</p>}
            {turn.error && <p className="error">{turn.error}</p>}
            {turn.response && (
              <>
                <p className="answer">{turn.response.answer}</p>
                <dl className="meta">
                  <div>
                    <dt>model</dt>
                    <dd>
                      {turn.response.provider}/{turn.response.model}
                    </dd>
                  </div>
                  <div>
                    <dt>latency</dt>
                    <dd>{turn.response.latency_ms} ms</dd>
                  </div>
                  <div>
                    <dt>tokens</dt>
                    <dd>
                      {turn.response.usage.prompt_tokens ?? "–"} in /{" "}
                      {turn.response.usage.completion_tokens ?? "–"} out
                    </dd>
                  </div>
                  <div>
                    <dt>run</dt>
                    <dd className="mono">{turn.response.run_id.slice(0, 8)}</dd>
                  </div>
                </dl>
              </>
            )}
          </article>
        ))}
      </main>
    </div>
  );
}
