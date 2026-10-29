import { type KeyboardEvent, useEffect, useRef } from "react";

import { BookIcon, SendIcon, StopIcon } from "./Icons";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  busy: boolean;
  disabled?: boolean;
  useKnowledgeBase: boolean;
  onToggleKnowledgeBase: () => void;
}

const MAX_CHARS = 8000;

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  disabled,
  useKnowledgeBase,
  onToggleKnowledgeBase,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with content up to a cap, then scroll. Modern browsers do this in CSS
  // (field-sizing: content); this is the fallback for the rest.
  useEffect(() => {
    const el = ref.current;
    if (!el || CSS.supports("field-sizing", "content")) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  useEffect(() => {
    if (!busy) ref.current?.focus();
  }, [busy]);

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!busy) onSubmit();
    }
  }

  const nearLimit = value.length > MAX_CHARS * 0.9;

  return (
    <div className="composer-wrap">
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (!busy) onSubmit();
        }}
      >
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            useKnowledgeBase ? "Ask about company policies, incidents, processes…" : "Ask anything…"
          }
          rows={1}
          maxLength={MAX_CHARS}
          aria-label="Message"
          disabled={disabled}
        />
        <button
          type="button"
          className={`kb-toggle ${useKnowledgeBase ? "on" : ""}`}
          onClick={onToggleKnowledgeBase}
          aria-pressed={useKnowledgeBase}
          title={useKnowledgeBase ? "Answers use company documents" : "Company documents are off"}
        >
          <BookIcon width={15} height={15} />
          <span>Company docs</span>
        </button>
        {busy ? (
          <button type="button" className="send-button stop" onClick={onStop} aria-label="Stop">
            <StopIcon />
          </button>
        ) : (
          <button
            type="submit"
            className="send-button"
            disabled={disabled || !value.trim()}
            aria-label="Send"
          >
            <SendIcon />
          </button>
        )}
      </form>
      <div className="composer-foot">
        <span>
          <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
        </span>
        {nearLimit ? (
          <span className="char-count">
            {value.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
          </span>
        ) : (
          <span>AI answers can be wrong. Verify important information.</span>
        )}
      </div>
    </div>
  );
}
