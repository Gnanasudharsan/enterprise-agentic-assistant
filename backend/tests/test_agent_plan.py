import json

import pytest

from app.agents.catalog import match_certified
from app.agents.plan import Plan, fallback_plan, parse_plan
from app.agents.tables import chart_hint, to_markdown


def plan_json(*steps: tuple[str, str]) -> str:
    return json.dumps(
        {
            "reasoning": "test",
            "steps": [
                {"id": f"s{i}", "agent": agent, "goal": f"goal {i}", "query": query}
                for i, (agent, query) in enumerate(steps, start=1)
            ],
        }
    )


def test_parse_plan_accepts_valid_plan():
    plan = parse_plan(plan_json(("research", "INC-204 root cause"), ("data", "tickets")), 4)
    assert [s.agent for s in plan.steps] == ["research", "data"]


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        ("not json", "not valid JSON"),
        ("[]", "steps"),
        ('{"steps": [{"id": "s1", "agent": "email", "goal": "x y z", "query": "x y z"}]}',
         "agent"),
        ('{"steps": [{"id": "s1", "agent": "data", "goal": "abc", "query": "abc"},'
         ' {"id": "s1", "agent": "data", "goal": "abc", "query": "abc"}]}', "unique"),
        (plan_json(*[("research", "query")] * 3, ("data", "query"), ("data", "query")),
         "too many steps"),
    ],
)  # fmt: skip
def test_parse_plan_rejects_invalid_plans(raw, problem):
    with pytest.raises(ValueError, match=problem):
        parse_plan(raw, 4)


def test_fallback_plan_routes_by_question():
    assert fallback_plan("hello!").steps == []
    assert [s.agent for s in fallback_plan("What is the PTO carry-over policy?").steps] == [
        "research"
    ]
    assert [s.agent for s in fallback_plan("How many tickets did we get in September?").steps] == [
        "research",
        "data",
    ]


def test_match_certified_by_keywords():
    assert match_certified("kyb verification tickets per month").key == "kyb_tickets_by_month"
    assert match_certified("why did onboarding time slow down").key == "onboarding_time_by_month"
    assert match_certified("what is the PTO policy") is None


def test_chart_hint_shapes():
    rows = [["2026-07", 6, 200.5], ["2026-08", 9, 180.0], ["2026-09", 118, 300.1]]
    assert chart_hint(["month", "tickets", "avg_minutes"], rows) == {
        "type": "bar",
        "x": "month",
        "y": ["avg_minutes", "tickets"],  # the headline measure first
    }
    grouped = [["2026-07", "Standard", 48, 2.4], ["2026-07", "Enterprise", 10, 7.9]]
    assert chart_hint(["month", "plan", "customers", "median_days"], grouped) == {
        "type": "bar",
        "x": "month",
        "group": "plan",
        "y": ["median_days", "customers"],
    }
    assert chart_hint(["total"], [[3]]) is None
    assert chart_hint(["customer_id", "name"], [[1, "a"], [2, "b"]]) is None


def test_to_markdown_limits_rows_and_escapes():
    md = to_markdown(["a", "b"], [["x|y", 1.50]] * 3, limit=2)
    assert "x\\|y | 1.5" in md
    assert md.endswith("(+1 more rows not shown)")


def test_target_questions_always_get_research():
    from app.agents.plan import apply_plan_rules

    plan = parse_plan(plan_json(("data", "median onboarding by month")), 4)
    adjusted, notes = apply_plan_rules(plan, "Did we meet the 3-day onboarding target?")
    assert [s.agent for s in adjusted.steps] == ["data", "research"]
    assert adjusted.steps[1].id == "s2" and notes

    measured, notes = apply_plan_rules(plan, "How many tickets in September?")
    assert [s.agent for s in measured.steps] == ["data", "research"]
    assert notes == ["added a research step: every question checks the documents"]


def test_every_question_checks_the_documents_except_small_talk():
    from app.agents.plan import apply_plan_rules

    empty = Plan(reasoning="general knowledge", steps=[])
    adjusted, _ = apply_plan_rules(empty, "What is the max hotel rate in San Francisco?")
    assert [(s.agent, s.query) for s in adjusted.steps] == [
        ("research", "What is the max hotel rate in San Francisco?")
    ]
    for message in ("Thanks, that's really helpful!", "hi", "Great, thank you."):
        assert apply_plan_rules(empty, message) == (empty, [])

    researched = parse_plan(plan_json(("research", "PTO policy")), 4)
    assert apply_plan_rules(researched, "How much PTO do I get?") == (researched, [])
    full = parse_plan(plan_json(*[("data", f"metric {i}") for i in range(3)]), 4)
    assert apply_plan_rules(full, "Compare three metrics", max_steps=3) == (full, [])


def test_added_research_step_keeps_the_action_last():
    from app.agents.plan import apply_plan_rules

    plan = parse_plan(plan_json(("data", "tickets"), ("action", "file it")), 4, actions=True)
    adjusted, _ = apply_plan_rules(plan, "Count tickets and file an issue")
    assert [s.agent for s in adjusted.steps] == ["data", "research", "action"]
