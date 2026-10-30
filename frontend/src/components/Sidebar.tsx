import type { Conversation } from "../storage";
import type { ThemePreference } from "../theme";
import {
  BookIcon,
  ChartIcon,
  LogoMark,
  MonitorIcon,
  MoonIcon,
  PlusIcon,
  SearchIcon,
  ShieldIcon,
  SparkIcon,
  SunIcon,
  TicketIcon,
  TrashIcon,
} from "./Icons";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  open: boolean;
  documentCount: number | null;
  groups: string[];
  theme: ThemePreference;
  onTheme: (t: ThemePreference) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onOpenKnowledgeBase: () => void;
  onOpenPalette: () => void;
  onOpenActions: () => void;
  pendingActions: number;
}

const ROADMAP = [
  { icon: ShieldIcon, label: "Safety evals", phase: "P5" },
  { icon: SparkIcon, label: "Baseline vs. agents", phase: "P5" },
  { icon: ChartIcon, label: "Cloud deployment", phase: "P6" },
];

const THEMES: { value: ThemePreference; icon: typeof SunIcon; label: string }[] = [
  { value: "light", icon: SunIcon, label: "Light" },
  { value: "dark", icon: MoonIcon, label: "Dark" },
  { value: "system", icon: MonitorIcon, label: "System" },
];

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
export const MOD_KEY = isMac ? "⌘" : "Ctrl";

function groupByDate(conversations: Conversation[]): [string, Conversation[]][] {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const day = 86_400_000;
  const buckets: [string, (t: number) => boolean][] = [
    ["Today", (t) => t >= startOfToday],
    ["Yesterday", (t) => t >= startOfToday - day],
    ["Previous 7 days", (t) => t >= startOfToday - 7 * day],
    ["Older", () => true],
  ];
  const groups = new Map<string, Conversation[]>();
  for (const c of conversations) {
    const [label] = buckets.find(([, test]) => test(c.updatedAt))!;
    groups.set(label, [...(groups.get(label) ?? []), c]);
  }
  return buckets.map(([label]) => label).filter((l) => groups.has(l)).map((l) => [l, groups.get(l)!]);
}

export function Sidebar(props: Props) {
  const { conversations, activeId, open, documentCount, groups, theme } = props;

  return (
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`} aria-label="Sidebar">
      <div className="brand">
        <span className="brand-mark">
          <LogoMark width={18} height={18} />
        </span>
        <div>
          <div className="brand-name">Helio Assistant</div>
          <div className="brand-sub">Research &amp; workflow AI</div>
        </div>
      </div>

      <button type="button" className="new-chat" onClick={props.onNew}>
        <PlusIcon width={16} height={16} /> New chat
      </button>
      <button type="button" className="sb-search" onClick={props.onOpenPalette}>
        <SearchIcon width={15} height={15} /> Search
        <kbd>{MOD_KEY} K</kbd>
      </button>
      <button type="button" className="nav-item" onClick={props.onOpenKnowledgeBase}>
        <BookIcon width={16} height={16} /> Knowledge base
        {documentCount != null && <span className="nav-count">{documentCount}</span>}
      </button>
      <button type="button" className="nav-item" onClick={props.onOpenActions}>
        <TicketIcon width={16} height={16} /> Actions
        {props.pendingActions > 0 && (
          <span className="nav-count nav-count-alert" title="Waiting for your approval">
            {props.pendingActions}
          </span>
        )}
      </button>

      <nav className="history" aria-label="Conversations">
        {conversations.length === 0 && (
          <>
            <div className="section-label">Recent</div>
            <p className="history-empty">Your conversations will appear here.</p>
          </>
        )}
        {groupByDate(conversations).map(([label, items]) => (
          <div key={label} className="history-group">
            <div className="section-label">{label}</div>
            {items.map((c) => (
              <div key={c.id} className={`history-item ${c.id === activeId ? "active" : ""}`}>
                <button
                  type="button"
                  className="history-open"
                  onClick={() => props.onSelect(c.id)}
                  aria-current={c.id === activeId ? "page" : undefined}
                >
                  <span className="history-title">{c.title}</span>
                </button>
                <button
                  type="button"
                  className="icon-button history-delete"
                  onClick={() => props.onDelete(c.id)}
                  aria-label={`Delete conversation ${c.title}`}
                  title="Delete"
                >
                  <TrashIcon width={14} height={14} />
                </button>
              </div>
            ))}
          </div>
        ))}
      </nav>

      <div className="roadmap">
        <div className="section-label">On the roadmap</div>
        {ROADMAP.map(({ icon: RoadIcon, label, phase }) => (
          <div key={label} className="roadmap-item">
            <RoadIcon width={14} height={14} />
            <span>{label}</span>
            <span className="roadmap-phase">{phase}</span>
          </div>
        ))}
      </div>

      <div className="user-card">
        <span className="user-avatar" aria-hidden="true">
          DU
        </span>
        <div className="user-meta">
          <div className="user-name">Demo user</div>
          <div className="user-groups" title={`Access groups: ${groups.join(", ")}`}>
            {groups.join(" · ")}
          </div>
        </div>
        <div className="theme-switch" role="radiogroup" aria-label="Theme">
          {THEMES.map(({ value, icon: TIcon, label }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={theme === value}
              className={`theme-btn ${theme === value ? "active" : ""}`}
              onClick={() => props.onTheme(value)}
              title={label}
            >
              <TIcon width={13} height={13} />
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
