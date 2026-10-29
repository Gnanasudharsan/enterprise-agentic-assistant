import { BulbIcon, CompassIcon, LogoMark, ShieldIcon, SparkIcon } from "./Icons";

const SUGGESTIONS = [
  {
    icon: BulbIcon,
    title: "Diagnose the onboarding slowdown",
    prompt: "Why did customer onboarding slow down in September, and what is being done about it?",
  },
  {
    icon: CompassIcon,
    title: "Check a policy",
    prompt: "How many unused PTO days carry over to next year, and when do they expire?",
  },
  {
    icon: ShieldIcon,
    title: "Understand an incident",
    prompt: "Summarize INC-204: impact, root cause, and remediation.",
  },
  {
    icon: SparkIcon,
    title: "Find the right approver",
    prompt: "Who needs to approve a $4,500 expense, and what receipts do I need?",
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
        Ask about Helio's policies, procedures, and incidents. Answers are grounded in the company
        knowledge base, with citations you can open and check.
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
