// Visual language for document types: a color token and a short label.

const TYPES: Record<string, { label: string; tone: string }> = {
  policy: { label: "Policy", tone: "blue" },
  procedure: { label: "Procedure", tone: "green" },
  incident: { label: "Incident", tone: "red" },
  adr: { label: "Decision", tone: "violet" },
  playbook: { label: "Playbook", tone: "amber" },
  spec: { label: "Spec", tone: "cyan" },
  plan: { label: "Plan", tone: "pink" },
};

export function docType(type: string | null | undefined) {
  return TYPES[type ?? ""] ?? { label: type ? type[0].toUpperCase() + type.slice(1) : "Document", tone: "gray" };
}

/** "Employee Handbook › Paid time off" → "Paid time off" (the part after the title). */
export function sectionLabel(section: string, title: string): string {
  const rest = section.split(" › ").slice(1).join(" › ");
  return rest || title;
}
