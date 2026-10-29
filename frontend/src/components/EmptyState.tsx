import { BulbIcon, CompassIcon, LogoMark, ShieldIcon, SparkIcon } from "./Icons";

const SUGGESTIONS = [
  {
    icon: CompassIcon,
    title: "Plan an onboarding week",
    prompt: "What should a new employee do in their first week? Give me a day-by-day plan.",
  },
  {
    icon: BulbIcon,
    title: "Diagnose slow onboarding",
    prompt:
      "Our customer onboarding time increased last month. What are the most likely causes and how should we investigate them?",
  },
  {
    icon: ShieldIcon,
    title: "Draft an incident summary",
    prompt:
      "Write a template for a post-incident report for a 2-hour API outage, with the sections an engineering leader expects.",
  },
  {
    icon: SparkIcon,
    title: "Compare two approaches",
    prompt:
      "Compare buying vs. building an internal knowledge-base search tool. Use a table for cost, time to value, and risk.",
  },
];

export function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="empty">
      <div className="empty-mark">
        <LogoMark width={28} height={28} />
      </div>
      <h1 className="empty-title">How can I help today?</h1>
      <p className="empty-sub">
        Ask about policies, processes, analysis, or planning. Answers stream in real time and keep
        the context of your conversation.
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map(({ icon: SIcon, title, prompt }) => (
          <button type="button" key={title} className="suggestion" onClick={() => onPick(prompt)}>
            <SIcon className="suggestion-icon" />
            <span className="suggestion-title">{title}</span>
            <span className="suggestion-prompt">{prompt}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
