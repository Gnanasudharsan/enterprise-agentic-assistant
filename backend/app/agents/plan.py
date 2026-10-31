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

AgentName = Literal["research", "data", "action"]


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
    def _one_action(self) -> "Plan":
        actions = [s for s in self.steps if s.agent == "action"]
        if len(actions) > 1:
            raise ValueError("at most 1 action step")
        if actions and actions[0].depends_on:
            raise ValueError("the action step always runs last; leave its depends_on empty")
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

{{action_agent}}
{SCHEMA_DOC}
Rules:
- Use the fewest steps that fully answer the question. Most questions need one or two.
- Questions that ask "why", "what changed", or "what is being done" about a measured \
change usually need both: data to quantify it and research to explain it.
- When a question measures something against a company target, policy, or plan (e.g. \
"did we meet the onboarding target?"), add research too, so the target is cited from the \
document that defines it.
- Questions about what a policy, procedure, or playbook says (limits, targets, response \
times, how long a process step takes, who approves) are research questions, even when a \
related column exists in the data. Use data for what was actually measured.
- Purely conversational messages (greetings, thanks) need no steps (empty list).
- Each data step asks one focused analytical question (one result table).
- If a data step needs facts that only the documents contain (incident dates, a target, a \
definition), set its "depends_on" to that research step's id: it then runs after the \
research and sees its findings. Otherwise leave "depends_on" empty so steps run in parallel.
- Write research queries as search phrases with the key terms (e.g. "INC-204 verification \
timeouts root cause remediation").
- At most {{max_steps}} steps in total.{{action_rule}}

Return only JSON:
{{{{"reasoning": "<one sentence>", "steps": [{{{{"id": "s1", \
"agent": "research" | "data"{{agent_choice}}, "goal": "<what this step finds out>", \
"query": "<search query or analytical question>", \
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
_SMALL_TALK = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|thx|ok|okay|cool|great|perfect|awesome|nice)\b", re.I
)


def is_small_talk(message: str) -> bool:
    """Greetings and thanks, not questions: the only messages answered without a lookup."""
    return bool(_CHAT_ONLY.match(message) or (_SMALL_TALK.match(message) and "?" not in message))


ACTION_AGENT = """\
- "action": drafts ONE issue in the company tracker (a ticket, task, or follow-up) for a \
human to review and approve. Nothing is created without approval. Use it only when the \
employee explicitly asks to create, file, open, log, or raise an issue/ticket/task.
"""
ACTION_RULE = """
- An action step runs last, after the answer is written, and sees all the evidence. \
Gather the evidence it needs with research/data steps. At most one action step."""
_ACTION_REQUEST = re.compile(
    r"\b(create|file|open|log|raise|draft|make|submit)\b.{0,40}\b(issue|ticket|task|"
    r"follow[- ]?up|bug report)s?\b",
    re.I,
)


def planner_messages(
    question: str, history: list[ChatMessage], max_steps: int, actions: bool = False
) -> list:
    context = ""
    if history:
        recent = "\n".join(f"{m.role}: {m.content[:400]}" for m in history[-4:])
        context = f"Recent conversation (for context only):\n{recent}\n\n"
    return [
        ChatMessage(
            role="system",
            content=PLANNER_PROMPT.format(
                max_steps=max_steps,
                action_agent=ACTION_AGENT if actions else "",
                action_rule=ACTION_RULE if actions else "",
                agent_choice=' | "action"' if actions else "",
            ),
        ),
        ChatMessage(role="user", content=f"{context}Question: {question}"),
    ]


def parse_plan(raw: str, max_steps: int, actions: bool = False) -> Plan:
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
    if not actions and any(s.agent == "action" for s in plan.steps):
        raise ValueError('the "action" agent is not available')
    return plan


def apply_plan_rules(plan: Plan, question: str, max_steps: int = 6) -> tuple[Plan, list[str]]:
    """Deterministic rules on top of the model's plan. Returns the plan and what changed.

    Every question that is not small talk also searches the documents. A research step is
    one retrieval (no model call) and runs in parallel with the other steps, so it costs
    little; skipping it is how a planner answers "what is the P1 response time?" from
    ticket data instead of the playbook, or "the hotel limit in San Francisco?" from
    general knowledge. A measured answer to "did we meet the target?" likewise needs the
    target cited from the document that defines it.
    """
    if (
        any(s.agent == "research" for s in plan.steps)
        or is_small_talk(question)
        or len(plan.steps) >= max_steps
    ):
        return plan, []
    steps = [s for s in plan.steps if s.agent != "action"]
    action = [s for s in plan.steps if s.agent == "action"]
    target = bool(steps) and bool(_REFERENCES_STANDARD.search(question))
    step = PlanStep(
        id=next(f"s{i}" for i in range(1, 10) if f"s{i}" not in {s.id for s in plan.steps}),
        agent="research",
        goal="Find where the target or policy is defined"
        if target
        else "Check the company documents",
        query=question[:500],
    )
    # The action step stays last.
    plan = plan.model_copy(update={"steps": [*steps, step, *action]})
    reason = (
        "the question refers to a target or policy"
        if target
        else "every question checks the documents"
    )
    return plan, [f"added a research step: {reason}"]


def fallback_plan(question: str, actions: bool = False) -> Plan:
    """A deterministic plan when the model cannot plan (offline mode, provider errors)."""
    if is_small_talk(question):
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
    if actions and _ACTION_REQUEST.search(question):
        steps.append(
            PlanStep(id=f"s{len(steps) + 1}", agent="action",
                     goal="Draft a tracker issue for the requested follow-up", query=question[:500])
        )  # fmt: skip
    return Plan(reasoning="Keyword-based plan (the model did not return a valid plan).",
                steps=steps)  # fmt: skip
