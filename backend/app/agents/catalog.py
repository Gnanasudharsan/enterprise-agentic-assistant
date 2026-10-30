"""Certified queries: reviewed SQL for the company's core metrics.

They serve two purposes: worked examples in the data agent's prompt (so generated SQL
follows the same conventions), and a deterministic fallback when no model is connected
or generated SQL keeps failing. Matching is by keyword overlap with the step's question.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CertifiedQuery:
    key: str
    title: str
    keywords: frozenset[str]
    sql: str


CERTIFIED_QUERIES = (
    CertifiedQuery(
        key="onboarding_time_by_month",
        title="Median onboarding time by signing month and plan (business days)",
        keywords=frozenset(
            {
                "onboarding",
                "time",
                "median",
                "slow",
                "slowdown",
                "slowed",
                "long",
                "days",
                "faster",
                "target",
                "plan",
                "duration",
                "took",
                "month",
            }
        ),  # fmt: skip
        sql="""\
SELECT to_char(contract_signed_on, 'YYYY-MM') AS month,
       plan,
       count(*) AS customers_live,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY onboarding_business_days)::numeric, 1)
         AS median_days,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY onboarding_business_days)::numeric, 1)
         AS p90_days
FROM analytics.customers
WHERE went_live_on IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2""",
    ),
    CertifiedQuery(
        key="kyb_tickets_by_month",
        title="Onboarding-related support tickets by month and tag",
        keywords=frozenset(
            {
                "ticket",
                "tickets",
                "support",
                "kyb",
                "verification",
                "volume",
                "tag",
                "escalation",
                "cluster",
                "backlog",
            }
        ),  # fmt: skip
        sql="""\
SELECT to_char(created_at, 'YYYY-MM') AS month,
       count(*) FILTER (WHERE tag = 'kyb-verification') AS kyb_verification,
       count(*) FILTER (WHERE tag = 'data-import') AS data_import,
       count(*) FILTER (WHERE tag = 'provisioning') AS provisioning,
       count(*) AS all_tickets
FROM analytics.support_tickets
GROUP BY 1
ORDER BY 1""",
    ),
    CertifiedQuery(
        key="verification_timeouts_by_week",
        title="Verification (KYB) timeout rate by week",
        keywords=frozenset(
            {
                "timeout",
                "timeouts",
                "verification",
                "kyb",
                "veritrust",
                "provider",
                "latency",
                "rate",
                "incident",
                "week",
                "failures",
            }
        ),  # fmt: skip
        sql="""\
SELECT to_char(date_trunc('week', requested_at), 'YYYY-MM-DD') AS week_starting,
       count(*) AS checks,
       count(*) FILTER (WHERE result = 'timeout') AS timeouts,
       round(100.0 * count(*) FILTER (WHERE result = 'timeout') / count(*), 1) AS timeout_pct,
       round(avg(latency_ms)) AS avg_latency_ms
FROM analytics.verification_checks
GROUP BY 1
ORDER BY 1""",
    ),
    CertifiedQuery(
        key="kyb_stage_time_by_month",
        title="Time spent in KYB verification by month (business hours)",
        keywords=frozenset(
            {
                "kyb",
                "verification",
                "stage",
                "hours",
                "blocking",
                "step",
                "bottleneck",
                "stages",
                "where",
            }
        ),  # fmt: skip
        sql="""\
SELECT to_char(started_at, 'YYYY-MM') AS month,
       count(*) AS customers,
       round(avg(business_hours), 1) AS avg_hours,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY business_hours)::numeric, 1)
         AS median_hours,
       count(*) FILTER (WHERE business_hours > 8) AS over_one_day
FROM analytics.onboarding_events
WHERE stage = 'kyb_verification' AND completed_at IS NOT NULL
GROUP BY 1
ORDER BY 1""",
    ),
    CertifiedQuery(
        key="signups_by_month",
        title="New customers by month, plan, and ARR",
        keywords=frozenset(
            {
                "customers",
                "signups",
                "signed",
                "new",
                "arr",
                "revenue",
                "growth",
                "region",
                "segment",
                "contracts",
            }
        ),  # fmt: skip
        sql="""\
SELECT to_char(contract_signed_on, 'YYYY-MM') AS month,
       count(*) AS new_customers,
       count(*) FILTER (WHERE plan = 'Enterprise') AS enterprise,
       sum(arr_usd) AS new_arr_usd
FROM analytics.customers
GROUP BY 1
ORDER BY 1""",
    ),
)

_WORD = re.compile(r"[a-z]+")


def match_certified(question: str) -> CertifiedQuery | None:
    words = set(_WORD.findall(question.lower()))
    best, best_score = None, 0
    for query in CERTIFIED_QUERIES:
        score = len(words & query.keywords)
        if score > best_score:
            best, best_score = query, score
    return best if best_score >= 2 else None


def examples_for_prompt(limit: int = 3) -> str:
    return "\n\n".join(f"-- {q.title}\n{q.sql};" for q in CERTIFIED_QUERIES[:limit])
