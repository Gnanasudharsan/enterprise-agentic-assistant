import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { untrustedComponents } from "./markdown";

import type { IssueArguments, Source, TableResult, ToolInfo } from "../api";
import type { Message } from "../storage";
import { ActionCard } from "./ActionCard";
import { AgentSteps } from "./Agent";
import { DataCard } from "./DataCard";
import { CheckIcon, CopyIcon, LogoMark, RetryIcon } from "./Icons";
import { CitationChip, ResearchSteps, SourceStrip, TableChip } from "./Research";

interface Props {
  message: Message;
  isLast: boolean;
  onRetry: () => void;
  onOpenSource: (source: Source) => void;
  onOpenTrace: (runId: string) => void;
  onResume: () => void;
  onDecide: (actionId: string, decision: "approve" | "reject", args?: IssueArguments) => void;
  tools: ToolInfo[];
  busy: boolean;
  onCopied: () => void;
}

/** Turn [S1] / [T1] markers into links that the Markdown renderer maps to chips. */
function linkCitations(text: string): string {
  return text.replace(/\[S(\d+)\]/g, "[$1](#cite-$1)").replace(/\[T(\d+)\]/g, "[T$1](#table-$1)");
}

/** Copy-friendly text: citation markers become plain [1] / [T1] references. */
function plainText(text: string): string {
  return text.replace(/\[S(\d+)\]/g, "[$1]");
}

function tableAnchor(messageId: string, n: number): string {
  return `table-${messageId}-${n}`;
}

function CopyButton({ text, onCopied }: { text: string; onCopied: () => void }) {
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
          onCopied();
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

export function MessageView({
  message,
  isLast,
  onRetry,
  onOpenSource,
  onOpenTrace,
  onResume,
  onDecide,
  tools,
  busy,
  onCopied,
}: Props) {
  if (message.role === "user") {
    return (
      <div className="msg msg-user">
        <div className="bubble">{message.content}</div>
      </div>
    );
  }

  const streaming = message.status === "streaming";
  const meta = message.meta;
  const sources = message.sources ?? [];
  const agent = message.agent;
  const tables: TableResult[] = agent?.tables ?? [];
  const tableCitations = agent?.tableCitations ?? [];
  const openTable = (n: number) => {
    const el = document.getElementById(tableAnchor(message.id, n));
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash");
    void el.offsetWidth; // restart the animation
    el.classList.add("flash");
  };

  return (
    <div className="msg msg-assistant">
      <div className="avatar" aria-hidden="true">
        <LogoMark width={15} height={15} />
      </div>
      <div className="msg-body">
        {agent ? (
          <AgentSteps message={message} onOpenTrace={() => agent.runId && onOpenTrace(agent.runId)} />
        ) : (
          <ResearchSteps message={message} />
        )}
        <SourceStrip
          sources={sources}
          citations={message.citations ?? []}
          settled={message.status === "done"}
          onOpen={onOpenSource}
        />

        {message.content && (
          <div className={`markdown ${streaming ? "is-streaming" : ""}`}>
            <Markdown
              remarkPlugins={[remarkGfm]}
              components={{
                ...untrustedComponents,
                a: ({ href, children, ...props }) => {
                  if (href?.startsWith("#table-")) {
                    const n = Number(href.slice(7));
                    return (
                      <TableChip
                        n={n}
                        table={tables.find((t) => t.index === n)}
                        onOpen={() => openTable(n)}
                      />
                    );
                  }
                  if (href?.startsWith("#cite-")) {
                    const n = Number(href.slice(6));
                    return (
                      <CitationChip
                        n={n}
                        source={sources.find((s) => s.index === n)}
                        onOpen={onOpenSource}
                      />
                    );
                  }
                  return (
                    <a href={href} {...props} target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  );
                },
              }}
            >
              {linkCitations(message.content)}
            </Markdown>
          </div>
        )}

        {tables.length > 0 && (
          <div className="data-cards">
            {tables.map((t) => (
              <DataCard
                key={t.step_id}
                table={t}
                id={t.index ? tableAnchor(message.id, t.index) : `table-${message.id}-${t.step_id}`}
                cited={message.status === "done" && t.index !== null && tableCitations.includes(t.index)}
              />
            ))}
          </div>
        )}

        {agent?.actions?.map((a) => (
          <ActionCard
            key={a.id}
            action={a}
            tool={tools.find((t) => t.name === a.tool)}
            busy={busy}
            onDecide={(decision, args) => onDecide(a.id, decision, args)}
          />
        ))}

        {message.status === "error" && (
          <div className="msg-error">
            <span>{message.error ?? "Something went wrong."}</span>
            {isLast && agent?.resumable && (
              <button type="button" className="text-button" onClick={onResume}>
                <RetryIcon width={14} height={14} /> Resume from last step
              </button>
            )}
            {isLast && (
              <button type="button" className="text-button" onClick={onRetry}>
                <RetryIcon width={14} height={14} /> Start over
              </button>
            )}
          </div>
        )}
        {message.status === "stopped" && <div className="msg-note">Generation stopped.</div>}

        {!streaming && message.content && (
          <div className="msg-toolbar">
            <CopyButton text={plainText(message.content)} onCopied={onCopied} />
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
            {agent?.model && (
              <span className="msg-meta" title={`Run ${agent.runId}`}>
                {agent.model.replace(/-\d{4}-\d{2}-\d{2}$/, "")} · multi-agent
              </span>
            )}
            {meta && (
              <span className="msg-meta" title={`Run ${meta.run_id}`}>
                {meta.model.replace(/-\d{4}-\d{2}-\d{2}$/, "")} · {meta.usage.prompt_tokens ?? "?"}→
                {meta.usage.completion_tokens ?? "?"} tok
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
