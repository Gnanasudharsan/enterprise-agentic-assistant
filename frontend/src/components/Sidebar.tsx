import type { Conversation } from "../storage";
import { ChartIcon, ChatIcon, DocIcon, LogoMark, PlusIcon, ShieldIcon, TrashIcon } from "./Icons";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  open: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

const ROADMAP = [
  { icon: DocIcon, label: "Document search with citations", phase: "Phase 2" },
  { icon: ChartIcon, label: "SQL analysis of business data", phase: "Phase 3" },
  { icon: ShieldIcon, label: "Actions with human approval", phase: "Phase 4" },
];

export function Sidebar({ conversations, activeId, open, onSelect, onNew, onDelete }: Props) {
  return (
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="brand">
        <span className="brand-mark">
          <LogoMark width={20} height={20} />
        </span>
        <div>
          <div className="brand-name">Enterprise Assistant</div>
          <div className="brand-sub">Research &amp; workflow AI</div>
        </div>
      </div>

      <button type="button" className="new-chat" onClick={onNew}>
        <PlusIcon /> New chat
      </button>

      <nav className="history" aria-label="Recent conversations">
        <div className="section-label">Recent</div>
        {conversations.length === 0 && <p className="history-empty">No conversations yet.</p>}
        {conversations.map((c) => (
          <div key={c.id} className={`history-item ${c.id === activeId ? "active" : ""}`}>
            <button type="button" className="history-open" onClick={() => onSelect(c.id)}>
              <ChatIcon width={15} height={15} />
              <span className="history-title">{c.title}</span>
            </button>
            <button
              type="button"
              className="icon-button history-delete"
              onClick={() => onDelete(c.id)}
              aria-label={`Delete conversation ${c.title}`}
              title="Delete"
            >
              <TrashIcon width={14} height={14} />
            </button>
          </div>
        ))}
      </nav>

      <div className="roadmap-card">
        <div className="section-label">Coming next</div>
        {ROADMAP.map(({ icon: RoadIcon, label, phase }) => (
          <div key={label} className="roadmap-item">
            <RoadIcon width={15} height={15} />
            <span>{label}</span>
            <span className="roadmap-phase">{phase}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}
