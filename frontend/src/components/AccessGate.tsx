import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { getAccess, setAccessCode, submitAccessCode } from "../api";

type State = "checking" | "open" | "locked";

/** Shows the app only after the deployment's access code (if it has one) is accepted. */
export function AccessGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>("checking");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAccess()
      .then((a) => setState(!a.required || a.granted ? "open" : "locked"))
      .catch(() => setState("open")); // backend unreachable: let the app show its offline state
    const lock = () => {
      setAccessCode(null);
      setState("locked");
    };
    window.addEventListener("eaa:access-required", lock);
    return () => window.removeEventListener("eaa:access-required", lock);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setBusy(true);
    const problem = await submitAccessCode(code.trim()).catch(() => "The server is unreachable.");
    setBusy(false);
    if (problem) setError(problem);
    else {
      setError(null);
      setState("open");
    }
  }

  if (state === "open") return <>{children}</>;
  if (state === "checking") return <div className="gate" aria-busy="true" />;
  return (
    <div className="gate">
      <form className="gate-card" onSubmit={submit}>
        <div className="gate-mark" aria-hidden="true" />
        <h1>Helio Assistant</h1>
        <p>
          A research and workflow assistant over a fictional company's documents and data. This
          demo uses a paid model, so it needs an access code.
        </p>
        <label htmlFor="access-code">Access code</label>
        <input
          id="access-code"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={code}
          onChange={(e) => setCode(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? "access-error" : undefined}
        />
        {error && (
          <p id="access-error" className="gate-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn btn-primary" disabled={busy || !code.trim()}>
          {busy ? "Checking…" : "Continue"}
        </button>
        <p className="gate-note">
          Code from the project owner. The source and evaluation reports are public on{" "}
          <a href="https://github.com/Gnanasudharsan/enterprise-agentic-assistant" target="_blank" rel="noreferrer">
            GitHub
          </a>
          .
        </p>
      </form>
    </div>
  );
}
