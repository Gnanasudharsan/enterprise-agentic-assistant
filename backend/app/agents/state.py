"""Graph state. Everything in it is plain JSON data, so every step can be checkpointed."""

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    question: str
    history: list[dict[str, str]]  # [{role, content}], oldest first
    groups: list[str]  # the caller's access groups, applied to every retrieval
    plan: dict[str, Any]  # a validated Plan, dumped
    # Results of the specialist steps. Steps run in parallel, so these lists are merged.
    research: Annotated[list[dict[str, Any]], operator.add]
    tables: Annotated[list[dict[str, Any]], operator.add]
    answer: str
    citations: dict[str, list[int]]  # {"sources": [...], "tables": [...]}
    invalid_citations: int
    model: str
    trace: Annotated[list[dict[str, Any]], operator.add]


class StepInput(TypedDict):
    """What a specialist receives for one plan step (sent with LangGraph's Send)."""

    step: dict[str, Any]
    question: str
    groups: list[str]
    # Findings of the research steps this step depends on (empty when it has none).
    context: str
