import { type KeyboardEvent, type RefObject, useEffect } from "react";

import { BookIcon, GlobeIcon, PaperclipIcon, SendIcon, StopIcon } from "./Icons";
import { MOD_KEY } from "./Sidebar";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  onAttach: () => void;
  busy: boolean;
  disabled?: boolean;
  useKnowledgeBase: boolean;
  onKnowledgeBaseChange: (on: boolean) => void;
  model?: string;
  variant: "hero" | "dock";
  inputRef: RefObject<HTMLTextAreaElement | null>;
}

const MAX_CHARS = 8000;

export function Composer(props: Props) {
  const { value, busy, disabled, useKnowledgeBase, variant, inputRef } = props;

  // Refocus after each answer, but not on touch devices, where focusing opens the
  // on-screen keyboard and scrolls the page.
  useEffect(() => {
    if (!busy && window.matchMedia("(pointer: fine)").matches) inputRef.current?.focus();
  }, [busy, inputRef]);

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!busy) props.onSubmit();
    }
  }

  const nearLimit = value.length > MAX_CHARS * 0.9;

  const box = (
    <form
      className={`composer ${variant === "hero" ? "hero-variant" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy) props.onSubmit();
      }}
    >
      <textarea
        ref={inputRef}
        value={value}
        onChange={(e) => props.onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={
          useKnowledgeBase
            ? "Ask about Helio's policies, incidents, decisions…"
            : "Ask anything (company documents are off)…"
        }
        rows={1}
        maxLength={MAX_CHARS}
        aria-label="Message"
        disabled={disabled}
      />
      <div className="composer-bar">
        <div className="composer-tools">
          <button
            type="button"
            className="icon-button"
            onClick={props.onAttach}
            title="Add a document to the knowledge base"
            aria-label="Add a document to the knowledge base"
          >
            <PaperclipIcon width={17} height={17} />
          </button>
          <div className="mode-switch" role="radiogroup" aria-label="Answer source">
            <button
              type="button"
              role="radio"
              aria-checked={useKnowledgeBase}
              className={`mode-option ${useKnowledgeBase ? "active" : ""}`}
              onClick={() => props.onKnowledgeBaseChange(true)}
              title="Ground answers in company documents, with citations"
            >
              <BookIcon width={14} height={14} />
              <span>Company docs</span>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={!useKnowledgeBase}
              className={`mode-option ${!useKnowledgeBase ? "active" : ""}`}
              onClick={() => props.onKnowledgeBaseChange(false)}
              title="Answer from the model's general knowledge only"
            >
              <GlobeIcon width={14} height={14} />
              <span>General</span>
            </button>
          </div>
        </div>
        <div className="composer-right">
          {nearLimit ? (
            <span className="char-count">
              {value.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
            </span>
          ) : (
            props.model && <span className="model-chip">{props.model}</span>
          )}
          {busy ? (
            <button type="button" className="send-button stop" onClick={props.onStop} aria-label="Stop">
              <StopIcon width={16} height={16} />
            </button>
          ) : (
            <button
              type="submit"
              className="send-button"
              disabled={disabled || !value.trim()}
              aria-label="Send"
            >
              <SendIcon width={17} height={17} />
            </button>
          )}
        </div>
      </div>
    </form>
  );

  if (variant === "hero") return box;
  return (
    <div className="composer-dock">
      {box}
      <div className="composer-foot">
        <span>
          <kbd>↵</kbd> send · <kbd>⇧</kbd>
          <kbd>↵</kbd> new line · <kbd>{MOD_KEY}</kbd>
          <kbd>K</kbd> commands
        </span>
        <span>Answers can be wrong. Check the cited sources.</span>
      </div>
    </div>
  );
}
