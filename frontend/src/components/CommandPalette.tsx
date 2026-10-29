import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import type { Conversation } from "../storage";
import { ChatIcon, SearchIcon } from "./Icons";

export interface Command {
  id: string;
  label: string;
  icon: ReactNode;
  hint?: string;
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  commands: Command[];
  conversations: Conversation[];
  onSelectConversation: (id: string) => void;
  onAsk: (prompt: string) => void;
}

function questionCount(c: Conversation): string {
  const n = c.messages.filter((m) => m.role === "user").length;
  return `${n} question${n === 1 ? "" : "s"}`;
}

/** ⌘K: jump to a conversation, run an action, or ask the query directly. */
export function CommandPalette(props: Props) {
  const { open, onClose, commands, conversations } = props;
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    const cmd = commands.filter((c) => !q || c.label.toLowerCase().includes(q));
    const convs = conversations
      .filter(
        (c) =>
          !q ||
          c.title.toLowerCase().includes(q) ||
          c.messages.some((m) => m.content.toLowerCase().includes(q)),
      )
      .slice(0, 8)
      .map<Command>((c) => ({
        id: `conv-${c.id}`,
        label: c.title,
        icon: <ChatIcon width={15} height={15} />,
        hint: questionCount(c),
        run: () => props.onSelectConversation(c.id),
      }));
    const ask: Command[] = q
      ? [
          {
            id: "ask",
            label: `Ask “${query.trim()}”`,
            icon: <SearchIcon width={15} height={15} />,
            hint: "new chat",
            run: () => props.onAsk(query.trim()),
          },
        ]
      : [];
    return { sections: [["Actions", cmd], ["Conversations", convs], ["Ask", ask]] as const };
  }, [query, commands, conversations]);

  const flat = items.sections.flatMap(([, list]) => list);

  if (!open) return null;

  function run(c: Command | undefined) {
    if (!c) return;
    onClose();
    c.run();
  }

  let index = -1;
  return (
    <div className="palette-scrim" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
          else if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, flat.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            run(flat[active]);
          }
        }}
      >
        <div className="palette-input-row">
          <SearchIcon width={18} height={18} />
          <input
            ref={inputRef}
            className="palette-input"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Search conversations, run a command, or ask a question…"
            aria-label="Command"
          />
          <kbd>esc</kbd>
        </div>
        <div className="palette-list">
          {flat.length === 0 && <div className="palette-empty">Nothing matches.</div>}
          {items.sections.map(([title, list]) =>
            list.length === 0 ? null : (
              <div key={title}>
                <div className="palette-section">{title}</div>
                {list.map((c) => {
                  index += 1;
                  const i = index;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      className={`palette-item ${i === active ? "active" : ""}`}
                      onMouseEnter={() => setActive(i)}
                      onClick={() => run(c)}
                    >
                      <span className="palette-item-icon">{c.icon}</span>
                      <span className="palette-item-label">{c.label}</span>
                      {c.hint && <span className="palette-item-hint">{c.hint}</span>}
                    </button>
                  );
                })}
              </div>
            ),
          )}
        </div>
        <div className="palette-foot">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span>
            <kbd>↵</kbd> select
          </span>
          <span>
            <kbd>esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
