import type { ReactNode } from "react";

import { BulbIcon, ChevronIcon, CompassIcon, LayersIcon, LogoMark, ShieldIcon, SparkIcon } from "./Icons";

const SUGGESTIONS = [
  {
    icon: BulbIcon,
    tone: "amber",
    title: "Diagnose the onboarding slowdown",
    prompt: "Why did customer onboarding slow down in September, and what is being done about it? Quantify it.",
  },
  {
    icon: ShieldIcon,
    tone: "red",
    title: "Brief me on an incident",
    prompt: "Summarize INC-204 and show the verification timeout rate by week.",
  },
  {
    icon: CompassIcon,
    tone: "blue",
    title: "File a follow-up for approval",
    prompt: "What remediation from INC-204 is still open? Create a follow-up issue for it.",
  },
  {
    icon: SparkIcon,
    tone: "violet",
    title: "Check a target against the data",
    prompt: "Did we meet the 3-day onboarding target for Standard plans in August, September, and October?",
  },
];

interface Props {
  onPick: (prompt: string) => void;
  composer: ReactNode;
  stats: { documents: number; passages: number } | null;
  embeddingModel?: string;
}

export function EmptyState({ onPick, composer, stats, embeddingModel }: Props) {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <div className="hero">
      <div className="hero-glow" aria-hidden="true" />
      <div className="hero-inner">
        <span className="hero-eyebrow">
          <span className="hero-eyebrow-mark">
            <LogoMark width={13} height={13} />
          </span>
          {greeting}.<span className="hero-eyebrow-more">Every answer cites its documents and data.</span>
        </span>
        <h1 className="hero-title">
          What should we <em>research</em> today?
        </h1>
        <p className="hero-sub">
          Ask about Helio's policies, incidents, decisions, and metrics. A team of agents plans
          the research, searches documents, queries company data, and shows its work.
        </p>

        {composer}

        <div className="hero-stats" aria-label="Knowledge base">
          {stats && (
            <>
              <span>
                <LayersIcon width={13} height={13} />
                <b>{stats.documents}</b> documents
              </span>
              <span>
                <b>{stats.passages}</b> passages
              </span>
            </>
          )}
          <span>
            <b>4</b> data tables
          </span>
          <span>multi-agent · docs + SQL</span>
          {embeddingModel && <span>{embeddingModel}</span>}
        </div>

        <div className="suggestions-label">Try asking</div>
        <div className="suggestions">
          {SUGGESTIONS.map(({ icon: SIcon, tone, title, prompt }) => (
            <button type="button" key={title} className="suggestion" onClick={() => onPick(prompt)}>
              <span className={`suggestion-icon tone-${tone}`}>
                <SIcon width={15} height={15} />
              </span>
              <span className="suggestion-title">{title}</span>
              <span className="suggestion-prompt">{prompt}</span>
              <ChevronIcon className="suggestion-go" width={16} height={16} />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
