"""Presenting query results: compact Markdown for the model and a chart hint for the UI."""

import re
from typing import Any

MAX_PROMPT_ROWS = 40
_TIME_COLUMN = re.compile(r"month|week|date|day|period|quarter|year", re.I)
_PREFERRED_METRIC = re.compile(r"median|avg|average|mean|pct|percent|rate|share", re.I)
_ID_COLUMN = re.compile(r"(^|_)id$", re.I)


def to_markdown(columns: list[str], rows: list[list[Any]], limit: int = MAX_PROMPT_ROWS) -> str:
    def cell(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.2f}".rstrip("0").rstrip(".")
        return str(v).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"(+{len(rows) - limit} more rows not shown)")
    return "\n".join(lines)


def _is_numeric(values: list[Any]) -> bool:
    present = [v for v in values if v is not None]
    return bool(present) and all(
        isinstance(v, int | float) and not isinstance(v, bool) for v in present
    )


def _is_label(values: list[Any]) -> bool:
    present = [v for v in values if v is not None]
    return bool(present) and all(isinstance(v, str) for v in present)


def chart_hint(columns: list[str], rows: list[list[Any]]) -> dict[str, Any] | None:
    """Suggest a simple chart: x = the first label column, y = up to 3 metrics, optionally
    split into series by a second label column (e.g. month x plan). None if not chartable."""
    if len(rows) < 2 or len(columns) < 2:
        return None
    by_column = {c: [r[i] for r in rows] for i, c in enumerate(columns)}
    labels = [c for c in columns if _is_label(by_column[c])]
    metrics = [c for c in columns if _is_numeric(by_column[c]) and not _ID_COLUMN.search(c)]
    if not labels or not metrics:
        return None
    # Lead with the headline measure (a median, rate...) rather than a supporting count.
    metrics.sort(key=lambda m: not _PREFERRED_METRIC.search(m))
    x = labels[0]
    kind = "line" if _TIME_COLUMN.search(x) and len({*by_column[x]}) >= 4 else "bar"
    if len(labels) >= 2:
        group = labels[1]
        if len({*by_column[group]}) > 6:
            return None
        return {"type": kind, "x": x, "group": group, "y": metrics[:3]}
    if len(rows) > 60:
        return None
    return {"type": kind, "x": x, "y": metrics[:3]}
