"""The supervisor's plan: which specialist agents to run, validated before execution.

The model proposes a plan as JSON; Pydantic enforces its shape and limits. An invalid
plan is sent back once with the validation error; if the model still cannot produce one
(or no model is connected), a deterministic keyword plan keeps the system working.
"""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.analytics.schema import SCHEMA_DOC
from app.llm.base import ChatMessage

AgentName = Literal["research", "data"]


class PlanStep(BaseModel):
    id: str = Field(pattern=r"^s[1-9]$")
    agent: AgentName
    # What this step should find out, in plain language (shown to the user).
    goal: str = Field(min_length=3, max_length=300)
    # research: the knowledge-base search query. data: the analytical question to answer
    # with SQL over the analytics schema.
    query: str = Field(min_length=3, max_length=500)
    # Research steps whose findings this step needs (e.g. incident dates for a data step).
    # A step with dependencies runs after them; steps without run in parallel.
    depends_on: list[str] = Field(default_factory=list, max_length=3)


class Plan(BaseModel):
    reasoning: str = Field(default="", max_length=600)
    steps: list[PlanStep] = Field(default_factory=list, max_length=6)

    @field_validator("steps")
    @classmethod
    def _unique_ids(cls, steps: list[PlanStep]) -> list[PlanStep]:
        ids = [s.id for s in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        return steps

    @model_validator(mode="after")
    def _per_agent_limit(self) -> "Plan":
        for agent in ("research", "data"):
            if sum(s.agent == agent for s in self.steps) > 3:
                raise ValueError(f"at most 3 {agent} steps")
        return self

    @model_validator(mode="after")
    def _dependencies(self) -> "Plan":
        # Only data steps may wait, and only for research steps: the graph stays two waves.
        research = {s.id for s in self.steps if s.agent == "research"}
        for s in self.steps:
            if s.depends_on and s.agent != "data":
                raise ValueError(f"{s.id}: only data steps can depend on other steps")
            unknown = set(s.depends_on) - research
            if unknown:
                raise ValueError(f"{s.id}: depends_on must list research step ids, not {unknown}")
        return self


PLANNER_PROMPT = f"""\
You are the supervisor of a team of agents that answer employees' questions at Helio \
Systems. Decide which specialists to use, then return a plan as a JSON object.

Specialists:
- "research": searches the company knowledge base (policies, procedures, incident \
reports, decision records, product docs, plans). Use it for what the company says, \
decided, or documented, and for explanations of why something happened.
- "data": writes and runs read-only SQL over the analytics database described below. \
Use it for counts, rates, trends, medians, comparisons, and anything measured.

{SCHEMA_DOC}
Rules:
- Use the fewest steps that fully answer the question. Most questions need one or two.
- Questions that ask "why", "what changed", or "what is being done" about a measured \
change usually need both: data to quantify it and research to explain it.
- When a question measures something against a company target, policy, or plan (e.g. \
"did we meet the onboarding target?"), add research too, so the target is cited from the \
document that defines it.
- Purely conversational or general-knowledge questions need no steps (empty list).
- Each data step asks one focused analytical question (one result table).
- If a data step needs facts that only the documents contain (incident dates, a target, a \
definition), set its "depends_on" to that research step's id: it then runs after the \
research and sees its findings. Otherwise leave "depends_on" empty so steps run in parallel.
- Write research queries as search phrases with the key terms (e.g. "INC-204 verification \
timeouts root cause remediation").
- At most {{max_steps}} steps in total.

Return only JSON:
{{{{"reasoning": "<one sentence>", "steps": [{{{{"id": "s1", "agent": "research" | "data", \
"goal": "<what this step finds out>", "query": "<search query or analytical question>", \
"depends_on": []}}}}]}}}}
"""

_DATA_HINTS = re.compile(
    r"\b(how many|number of|count|trend|rate|median|average|avg|mean|percent|%|per "
    r"(?:month|week|day)|by (?:month|week|plan|region|segment)|compare|comparison|metric|"
    r"metrics|volume|increase|decrease|slow(?:ed|down)?|faster|longer|tickets?|"
    r"onboarding time|how long|timeouts?|went live|go-live)\b",
    re.I,
)
_REFERENCES_STANDARD = re.compile(
    r"\b(target|targets|goal|goals|okrs?|sla|slas|policy|policies|procedure|commitment|"
    r"objective|benchmark|threshold)\b",
    re.I,
)
_CHAT_ONLY = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|cool)\b[\s!.?]*$", re.I)


def planner_messages(question: str, history: list[ChatMessage], max_steps: int) -> list:
    context = ""
    if history:
        recent = "\n".join(f"{m.role}: {m.content[:400]}" for m in history[-4:])
        context = f"Recent conversation (for context only):\n{recent}\n\n"
    return [
        ChatMessage(role="system", content=PLANNER_PROMPT.format(max_steps=max_steps)),
        ChatMessage(role="user", content=f"{context}Question: {question}"),
    ]


def parse_plan(raw: str, max_steps: int) -> Plan:
    """Validate the model's JSON. Raises ValueError with a message the model can act on."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict) or "steps" not in data:
        raise ValueError('expected an object with a "steps" list')
    try:
        plan = Plan.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'plan'}: {e['msg']}" for e in exc.errors()
        )
        raise ValueError(problems) from exc
    if len(plan.steps) > max_steps:
        raise ValueError(f"too many steps: {len(plan.steps)} > {max_steps}")
    return plan


def apply_plan_rules(plan: Plan, question: str) -> tuple[Plan, list[str]]:
    """Deterministic rules on top of the model's plan. Returns the plan and what changed.

    A measured answer to "did we meet the target?" is only trustworthy if the target is
    cited from the document that defines it, so such questions always get a research step.
    """
    notes: list[str] = []
    has_data = any(s.agent == "data" for s in plan.steps)
    has_research = any(s.agent == "research" for s in plan.steps)
    if has_data and not has_research and _REFERENCES_STANDARD.search(question):
        used = {s.id for s in plan.steps}
        new_id = next(f"s{i}" for i in range(1, 10) if f"s{i}" not in used)
        step = PlanStep(
            id=new_id,
            agent="research",
            goal="Find where the target or policy is defined",
            query=question[:500],
        )
        plan = plan.model_copy(update={"steps": [*plan.steps, step]})
        notes.append("added a research step: the question refers to a target or policy")
    return plan, notes


def fallback_plan(question: str) -> Plan:
    """A deterministic plan when the model cannot plan (offline mode, provider errors)."""
    if _CHAT_ONLY.match(question):
        return Plan(reasoning="Conversational message; no lookup needed.", steps=[])
    steps = [
        PlanStep(id="s1", agent="research", goal="Find relevant company documents",
                 query=question[:500])
    ]  # fmt: skip
    if _DATA_HINTS.search(question):
        steps.append(
            PlanStep(id="s2", agent="data", goal="Measure it in the analytics data",
                     query=question[:500])
        )  # fmt: skip
    return Plan(reasoning="Keyword-based plan (the model did not return a valid plan).",
                steps=steps)  # fmt: skip
