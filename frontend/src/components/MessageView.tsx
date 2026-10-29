import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Message } from "../storage";
import { CheckIcon, CopyIcon, LogoMark, RetryIcon } from "./Icons";

interface Props {
  message: Message;
  isLast: boolean;
  onRetry: () => void;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="icon-button"
      title={copied ? "Copied" : "Copy"}
      aria-label="Copy answer"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard blocked; nothing useful to do.
        }
      }}
    >
      {copied ? <CheckIcon width={15} height={15} /> : <CopyIcon width={15} height={15} />}
    </button>
  );
}

export function MessageView({ message, isLast, onRetry }: Props) {
  if (message.role === "user") {
    return (
      <div className="msg msg-user">
        <div className="bubble">{message.content}</div>
      </div>
    );
  }

  const streaming = message.status === "streaming";
  const waiting = streaming && message.content === "";
  const meta = message.meta;

  return (
    <div className="msg msg-assistant">
      <div className="avatar" aria-hidden="true">
        <LogoMark width={16} height={16} />
      </div>
      <div className="msg-body">
        {waiting ? (
          <div className="thinking" aria-label="Thinking">
            <span />
            <span />
            <span />
          </div>
        ) : (
          <div className={`markdown ${streaming ? "is-streaming" : ""}`}>
            <Markdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
              }}
            >
              {message.content}
            </Markdown>
          </div>
        )}

        {message.status === "error" && (
          <div className="msg-error">
            <span>{message.error ?? "Something went wrong."}</span>
            {isLast && (
              <button type="button" className="text-button" onClick={onRetry}>
                <RetryIcon width={14} height={14} /> Try again
              </button>
            )}
          </div>
        )}
        {message.status === "stopped" && <div className="msg-note">Generation stopped.</div>}

        {!streaming && message.content && (
          <div className="msg-toolbar">
            <CopyButton text={message.content} />
            {isLast && (
              <button
                type="button"
                className="icon-button"
                title="Regenerate"
                aria-label="Regenerate answer"
                onClick={onRetry}
              >
                <RetryIcon width={15} height={15} />
              </button>
            )}
            {meta && (
              <span className="msg-meta" title={`Run ${meta.run_id}`}>
                {meta.model} · {(meta.latency_ms / 1000).toFixed(1)}s
                {meta.usage.completion_tokens != null &&
                  ` · ${meta.usage.prompt_tokens ?? "?"} → ${meta.usage.completion_tokens} tokens`}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
