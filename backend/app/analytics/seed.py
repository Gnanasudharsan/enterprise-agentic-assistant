"""Deterministic synthetic data for the `analytics` schema.

The numbers tell the same story as the document corpus, so questions that need both
can be cross-checked: CS-004 v2.0 made KYB verification blocking on 2026-09-01, and
INC-204 (verification timeouts, 2026-09-08 to 2026-09-19) delayed 63 onboardings and
produced 118 `kyb-verification` tickets in September versus 9 in August. October is
better but still above the 3-business-day Standard target (the Q4 OKR).
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.analytics.schema import (
    SCHEMA,
    customers,
    onboarding_events,
    support_tickets,
    verification_checks,
)

SEED = 204
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)  # the dataset's "today"
DAY_START, DAY_END = 9, 17  # working hours, UTC
HOURS_PER_DAY = DAY_END - DAY_START

BLOCKING_KYB_FROM = datetime(2026, 9, 1, tzinfo=UTC)
INCIDENT_START = datetime(2026, 9, 8, tzinfo=UTC)
INCIDENT_END = datetime(2026, 9, 19, 17, tzinfo=UTC)
DELAYED_CUSTOMERS = 63
KYB_TICKETS = {7: 6, 8: 9, 9: 118, 10: 14}
SIGNUPS = {7: 58, 8: 62, 9: 104, 10: 71}

STAGES = ("kickoff", "kyb_verification", "provisioning", "data_import", "admin_training", "go_live")
# Typical business hours per stage on the Standard plan: (low, high).
STANDARD_HOURS = {
    "kickoff": (3, 8),
    "provisioning": (1, 2),
    "data_import": (4, 10),
    "admin_training": (2, 5),
    "go_live": (1, 2),
}
ENTERPRISE_FACTOR = 3.2

INDUSTRIES = (
    "Software", "Financial services", "Healthcare", "Retail", "Manufacturing",
    "Education", "Media", "Logistics", "Professional services", "Public sector",
)  # fmt: skip
NAME_A = (
    "Blue", "North", "Bright", "Silver", "Red", "Green", "Clear", "Swift", "Iron", "Cedar",
    "Lumen", "Harbor", "Summit", "Atlas", "Nova", "Pine", "Granite", "Coral", "Echo", "Prism",
)  # fmt: skip
NAME_B = (
    "Labs", "Analytics", "Health", "Logistics", "Retail", "Works", "Systems", "Bank",
    "Studios", "Partners", "Foods", "Energy", "Robotics", "Media", "Capital", "Freight",
)  # fmt: skip
OTHER_TAGS = (
    ("how-to", 30), ("bug", 22), ("billing", 14), ("data-import", 12),
    ("sso", 9), ("provisioning", 7), ("performance", 6),
)  # fmt: skip


def is_workday(d: date) -> bool:
    return d.weekday() < 5


def next_work_start(ts: datetime) -> datetime:
    """The next moment that is inside working hours (ts itself if it already is)."""
    if is_workday(ts.date()) and DAY_START <= ts.hour < DAY_END:
        return ts
    d = ts.date() if ts.hour < DAY_START else ts.date() + timedelta(days=1)
    while not is_workday(d):
        d += timedelta(days=1)
    return datetime.combine(d, time(DAY_START), tzinfo=UTC)


def add_business_hours(ts: datetime, hours: float) -> datetime:
    ts = next_work_start(ts)
    remaining = timedelta(hours=hours)
    while True:
        end_of_day = datetime.combine(ts.date(), time(DAY_END), tzinfo=UTC)
        if ts + remaining <= end_of_day:
            return ts + remaining
        remaining -= end_of_day - ts
        ts = next_work_start(end_of_day)


def workdays_in(year: int, month: int) -> list[date]:
    d, days = date(year, month, 1), []
    while d.month == month:
        if is_workday(d):
            days.append(d)
        d += timedelta(days=1)
    return days


@dataclass
class Customer:
    customer_id: int
    name: str
    plan: str
    segment: str
    region: str
    industry: str
    arr_usd: int
    signed: datetime
    stages: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    delayed: bool = False

    @property
    def kyb(self) -> dict:
        return self.stages[1]

    @property
    def live_at(self) -> datetime | None:
        return self.stages[-1]["completed_at"] if self.stages else None


@dataclass
class Dataset:
    customers: list[dict]
    onboarding_events: list[dict]
    verification_checks: list[dict]
    support_tickets: list[dict]


def _stage_hours(rng: random.Random, plan: str, stage: str) -> float:
    low, high = STANDARD_HOURS[stage]
    hours = rng.triangular(low, high)
    return hours * ENTERPRISE_FACTOR if plan == "Enterprise" else hours


def _kyb_hours(rng: random.Random, plan: str, starts: datetime, delayed: bool) -> float:
    if starts < BLOCKING_KYB_FROM:
        return rng.uniform(0.3, 1.0)  # ran in the background before CS-004 v2.0
    if delayed:
        return rng.uniform(14, 52)  # timeouts, manual restarts
    if starts <= INCIDENT_END + timedelta(days=5):
        return rng.uniform(3, 6)
    # After the fix: retries with backoff succeed, but rate limiting still adds time.
    hours = rng.uniform(4, 10)
    return hours * 1.5 if plan == "Enterprise" else hours


def _signing_days(rng: random.Random, month: int, count: int) -> list[date]:
    days = workdays_in(2026, month)
    if month == 10:
        days = [d for d in days if d < NOW.date()]
    # September's volume increase was concentrated in the first three weeks.
    weights = [5.0 if month == 9 and 7 <= d.day <= 18 else 1.0 for d in days]
    return sorted(rng.choices(days, weights=weights, k=count))


def _make_customers(rng: random.Random) -> list[Customer]:
    result: list[Customer] = []
    used_names: set[str] = set()
    for month, count in SIGNUPS.items():
        for day in _signing_days(rng, month, count):
            enterprise = rng.random() < 0.18
            plan = "Enterprise" if enterprise else "Standard"
            segment = (
                "Enterprise"
                if enterprise
                else rng.choices(("SMB", "Mid-Market"), weights=(65, 35))[0]
            )
            while True:
                name = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
                if name in used_names:
                    name = f"{name} {rng.choice(('Co', 'Group', 'Inc', 'Ltd', 'GmbH', 'AB'))}"
                if name not in used_names:
                    used_names.add(name)
                    break
            arr = (
                rng.randrange(90_000, 400_000, 500)
                if enterprise
                else rng.randrange(8_000, 60_000, 250)
            )
            signed = datetime.combine(day, time(rng.randint(DAY_START, DAY_END - 2)), tzinfo=UTC)
            result.append(
                Customer(
                    customer_id=len(result) + 1,
                    name=name,
                    plan=plan,
                    segment=segment,
                    region=rng.choices(("NA", "EMEA", "APAC"), weights=(55, 30, 15))[0],
                    industry=rng.choice(INDUSTRIES),
                    arr_usd=arr,
                    signed=signed + timedelta(minutes=rng.randint(0, 59)),
                )
            )
    return result


def _schedule(rng: random.Random, c: Customer, delayed_ids: set[int] | None) -> None:
    """Lay out the customer's onboarding stages. Without delayed_ids, a dry run that only
    finds when KYB would start."""
    c.stages = []
    ts = c.signed
    for stage in STAGES:
        start = next_work_start(ts)
        if stage == "kyb_verification":
            hours = _kyb_hours(
                rng, c.plan, start, bool(delayed_ids and c.customer_id in delayed_ids)
            )
        else:
            hours = _stage_hours(rng, c.plan, stage)
        end = add_business_hours(start, hours)
        c.stages.append({"stage": stage, "started_at": start, "completed_at": end, "hours": hours})
        ts = end


def _kyb_checks(rng: random.Random, c: Customer) -> None:
    start, end = c.kyb["started_at"], c.kyb["completed_at"]
    if c.delayed:
        attempts = rng.randint(2, 3)
        span = (end - start) / attempts
        for i in range(attempts - 1):
            c.checks.append({"at": start + span * i, "latency": 5000, "result": "timeout"})
        c.checks.append({"at": end - timedelta(minutes=5), "latency": rng.randint(6000, 9000),
                         "result": "passed"})  # fmt: skip
        return
    result = "manual_review" if rng.random() < 0.03 else "passed"
    latency = (
        rng.randint(6000, 9000)
        if INCIDENT_START <= start <= INCIDENT_END
        else rng.randint(600, 2600)
    )
    c.checks.append({"at": start + timedelta(minutes=rng.randint(1, 20)), "latency": latency,
                     "result": result})  # fmt: skip


def _background_checks(rng: random.Random, live: list[Customer]) -> list[dict]:
    """Periodic re-verification of existing customers: most of the provider traffic."""
    checks = []
    d = date(2026, 7, 1)
    while d < NOW.date():
        if is_workday(d):
            day_start = datetime.combine(d, time(DAY_START), tzinfo=UTC)
            pool = [c for c in live if c.signed < day_start]
            for _ in range(rng.randint(26, 38) if pool else 0):
                at = day_start + timedelta(minutes=rng.randint(0, HOURS_PER_DAY * 60 - 1))
                in_incident = INCIDENT_START <= at <= INCIDENT_END
                if in_incident and rng.random() < 0.02:
                    latency, result = 5000, "timeout"
                elif at > INCIDENT_END and rng.random() < 0.006:
                    latency, result = 15000, "timeout"
                else:
                    slow = in_incident or (at.month == 9 and at.day >= 2)
                    latency = (
                        rng.randint(6000, 9000)
                        if slow and rng.random() < 0.6
                        else (rng.randint(500, 2400))
                    )
                    result = "manual_review" if rng.random() < 0.01 else "passed"
                checks.append({"customer_id": rng.choice(pool).customer_id, "at": at,
                               "latency": latency, "result": result})  # fmt: skip
        d += timedelta(days=1)
    return checks


def _tickets(rng: random.Random, people: list[Customer]) -> list[dict]:
    tickets: list[dict] = []
    tags, weights = zip(*OTHER_TAGS, strict=True)

    def add(customer: Customer, created: datetime, tag: str, priority: str, surge: bool) -> None:
        minutes = {
            "P1": rng.randint(5, 20),
            "P2": rng.randint(20, 75),
            "P3": rng.randint(45, 300),
            "P4": rng.randint(120, 900),
        }[priority]
        if surge:
            minutes = int(minutes * rng.uniform(1.6, 2.6))  # backlog during INC-204
        resolve_hours = rng.uniform(2, 60) * (2 if surge else 1)
        resolved = created + timedelta(hours=resolve_hours)
        done = resolved < NOW
        tickets.append(
            {
                "customer_id": customer.customer_id,
                "created_at": created,
                "resolved_at": resolved if done else None,
                "priority": priority,
                "tag": tag,
                "status": "resolved" if done else "open",
                "first_response_minutes": minutes,
            }
        )

    for month, kyb_count in KYB_TICKETS.items():
        month_start = datetime(2026, month, 1, tzinfo=UTC)
        if month == 9:
            pool = [c for c in people if c.delayed]
            for i in range(kyb_count):
                c = pool[i % len(pool)]
                at = c.kyb["started_at"] + (c.kyb["completed_at"] - c.kyb["started_at"]) * (
                    rng.uniform(0.1, 0.9)
                )
                add(c, at, "kyb-verification", "P2" if rng.random() < 0.3 else "P3", True)
        else:
            pool = [c for c in people if c.kyb["started_at"].month == month] or people
            for _ in range(kyb_count):
                c = rng.choice(pool)
                at = c.kyb["started_at"] + timedelta(minutes=rng.randint(10, 240))
                add(c, min(at, NOW - timedelta(hours=1)), "kyb-verification", "P3", False)

        # Everything else: steady volume from customers already signed that month.
        candidates = [c for c in people if c.signed < month_start + timedelta(days=27)]
        for _ in range(rng.randint(140, 175)):
            day = rng.choice(workdays_in(2026, month))
            created = datetime.combine(day, time(rng.randint(DAY_START, DAY_END - 1)), tzinfo=UTC)
            created += timedelta(minutes=rng.randint(0, 59))
            if created >= NOW:
                continue
            eligible = [c for c in candidates if c.signed <= created] or candidates[:1]
            priority = rng.choices(("P1", "P2", "P3", "P4"), weights=(1, 8, 55, 36))[0]
            add(rng.choice(eligible), created, rng.choices(tags, weights=weights)[0], priority,
                False)  # fmt: skip

    tickets.sort(key=lambda t: t["created_at"])
    for i, t in enumerate(tickets, start=1):
        t["ticket_id"] = i
    return tickets


def generate() -> Dataset:
    rng = random.Random(SEED)
    people = _make_customers(rng)

    # Dry run to find who reached KYB during the incident, then choose the delayed ones.
    for c in people:
        _schedule(random.Random(SEED + c.customer_id), c, None)
    exposed = [c for c in people if INCIDENT_START <= c.kyb["started_at"] <= INCIDENT_END]
    if len(exposed) < DELAYED_CUSTOMERS:
        raise RuntimeError(f"only {len(exposed)} customers reached KYB during the incident")
    delayed_ids = {c.customer_id for c in rng.sample(exposed, DELAYED_CUSTOMERS)}

    for c in people:
        _schedule(random.Random(SEED + c.customer_id), c, delayed_ids)
        c.delayed = c.customer_id in delayed_ids
        _kyb_checks(rng, c)

    customer_rows, event_rows, check_rows = [], [], []
    for c in people:
        live_at = c.live_at if c.live_at and c.live_at <= NOW else None
        business_days = round(sum(s["hours"] for s in c.stages) / HOURS_PER_DAY, 1)
        customer_rows.append(
            {
                "customer_id": c.customer_id,
                "name": c.name,
                "plan": c.plan,
                "segment": c.segment,
                "region": c.region,
                "industry": c.industry,
                "arr_usd": c.arr_usd,
                "contract_signed_on": c.signed.date(),
                "went_live_on": live_at.date() if live_at else None,
                "onboarding_business_days": business_days if live_at else None,
            }
        )
        for s in c.stages:
            if s["started_at"] >= NOW:
                break
            done = s["completed_at"] <= NOW
            event_rows.append(
                {
                    "event_id": len(event_rows) + 1,
                    "customer_id": c.customer_id,
                    "stage": s["stage"],
                    "started_at": s["started_at"],
                    "completed_at": s["completed_at"] if done else None,
                    "business_hours": round(s["hours"], 1) if done else None,
                }
            )
        for chk in c.checks:
            if chk["at"] < NOW:
                check_rows.append({"customer_id": c.customer_id, **chk})

    live = [c for c in people if c.live_at and c.live_at <= NOW]
    check_rows.extend(_background_checks(rng, live))
    check_rows.sort(key=lambda r: r["at"])
    checks = [
        {
            "check_id": i,
            "customer_id": r["customer_id"],
            "requested_at": r["at"],
            "latency_ms": r["latency"],
            "result": r["result"],
        }
        for i, r in enumerate(check_rows, start=1)
    ]
    return Dataset(customer_rows, event_rows, checks, _tickets(rng, people))


async def seed(conn: AsyncConnection, *, force: bool = False) -> dict[str, int] | None:
    """Load the dataset. Returns row counts, or None if data was already present."""
    existing = await conn.scalar(select(func.count()).select_from(customers))
    if existing and not force:
        return None
    await conn.execute(
        text(
            f"TRUNCATE {SCHEMA}.support_tickets, {SCHEMA}.verification_checks, "
            f"{SCHEMA}.onboarding_events, {SCHEMA}.customers"
        )
    )
    data = generate()
    for table, rows in (
        (customers, data.customers),
        (onboarding_events, data.onboarding_events),
        (verification_checks, data.verification_checks),
        (support_tickets, data.support_tickets),
    ):
        await conn.execute(table.insert(), rows)
    return {
        "customers": len(data.customers),
        "onboarding_events": len(data.onboarding_events),
        "verification_checks": len(data.verification_checks),
        "support_tickets": len(data.support_tickets),
    }
