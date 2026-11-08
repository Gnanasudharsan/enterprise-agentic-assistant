// Every number on the site comes from here, and every number here comes from the
// repository: evals/reports/*.json (2026-10-31 runs), git history, and the ADRs.

export const links = {
  demo: "https://helio-assistant-vpgub2ic6q-uc.a.run.app",
  repo: "https://github.com/Gnanasudharsan/enterprise-agentic-assistant",
  benchmark: "https://github.com/Gnanasudharsan/enterprise-agentic-assistant/blob/main/evals/reports/benchmark-2026-10-31.md",
  benchmarkFirst: "https://github.com/Gnanasudharsan/enterprise-agentic-assistant/blob/main/evals/reports/benchmark-2026-10-31-initial.md",
  security: "https://github.com/Gnanasudharsan/enterprise-agentic-assistant/blob/main/evals/reports/security-2026-10-31.md",
  retrieval: "https://github.com/Gnanasudharsan/enterprise-agentic-assistant/blob/main/evals/reports/retrieval-2026-10-31.md",
  adrs: "https://github.com/Gnanasudharsan/enterprise-agentic-assistant/tree/main/docs/adr",
  author: "https://github.com/Gnanasudharsan",
};

export const author = "Gnanasudharsan Ashokumar";

export const headline = [
  { value: 91, suffix: "%", label: "task success on 32 held-out tasks", note: "vs. 56% for the best plain-RAG baseline" },
  { value: 20, suffix: "/20", label: "prompt-injection attacks defended", note: "direct and planted in documents" },
  { value: 0, suffix: "", label: "unauthorized actions", note: "9 live bypass attempts + 15 unit scenarios" },
  { value: 2.18, suffix: "", prefix: "$", decimals: 2, label: "per 1,000 questions", note: "every model call metered" },
];

// Benchmark: evals/reports/benchmark-2026-10-31.json (final) and -initial.json (held-out).
export const systems = [
  { key: "vector", name: "Vector RAG", sub: "vector search, one model call", color: "var(--s-1)" },
  { key: "hybrid", name: "Hybrid + rerank", sub: "vector + full-text, LLM rerank", color: "var(--s-2)" },
  { key: "agents", name: "Multi-agent", sub: "planner, docs + data agents, analyst", color: "var(--s-3)" },
] as const;

export const benchmark = {
  tasks: 32,
  success: { vector: 53, hybrid: 56, agents: 91 },
  firstRun: { vector: 53, hybrid: 56, agents: 78 },
  recall5: { vector: 95, hybrid: 100, agents: 100 },
  grounded: { vector: 99, hybrid: 99, agents: 100 },
  p50: { vector: 1.2, hybrid: 2.1, agents: 3.3 },
  p95: { vector: 2.2, hybrid: 3.4, agents: 5.7 },
  calls: { vector: 1.0, hybrid: 2.0, agents: 3.6 },
  costPer1k: { vector: 0.59, hybrid: 1.15, agents: 2.18 },
  categories: [
    { name: "Single document", n: 9, vector: 100, hybrid: 100, agents: 100 },
    { name: "Multi-document", n: 5, vector: 80, hybrid: 100, agents: 100 },
    { name: "Data (SQL)", n: 8, vector: 0, hybrid: 0, agents: 88 },
    { name: "Docs + data", n: 6, vector: 0, hybrid: 0, agents: 67 },
    { name: "Access-restricted", n: 2, vector: 100, hybrid: 100, agents: 100 },
    { name: "Unanswerable", n: 2, vector: 100, hybrid: 100, agents: 100 },
  ],
};

// evals/reports/retrieval-2026-10-31.json (37-question gold set, text-embedding-3-small).
export const rerankers = [
  { name: "Vector only", mrr: 0.883, recall: 97, ms: 224 },
  { name: "Hybrid (RRF)", mrr: 0.901, recall: 100, ms: 214 },
  { name: "MiniLM cross-encoder", mrr: 0.946, recall: 100, ms: 290 },
  { name: "BGE cross-encoder", mrr: 0.951, recall: 100, ms: 566 },
  { name: "LLM reranker", mrr: 0.968, recall: 100, ms: 1159, chosen: true },
];

// evals/reports/security-2026-10-31*.json
export const security = {
  attacks: 20,
  defendedFirst: 18,
  defended: 20,
  scenarios: 9,
  blocked: 9,
  unitScenarios: 15,
};

export const corpus = {
  documents: 12,
  restricted: 2,
  customers: 295,
  events: 1739,
  checks: 3123,
  tickets: 763,
};

export const code = {
  python: "6.6k",
  tests: "2.7k",
  frontend: "6.1k",
  unitTests: 175,
  integrationTests: 40,
  adrs: 7,
};
