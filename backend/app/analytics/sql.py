"""Read-only SQL for agents: a static validator plus a locked-down executor.

Model-written SQL is untrusted input. Two independent layers stop it from doing harm:

1. `validate_sql` parses the query (sqlglot) and rejects anything but a single SELECT
   over allow-listed `analytics` tables, using only allow-listed functions. It also
   caps the row count with a LIMIT.
2. `SQLExecutor` runs the query in a READ ONLY transaction, as the `analytics_reader`
   role (SELECT on the analytics schema only), with a statement timeout, and fetches at
   most `max_rows` rows. Even a query that slipped past the validator cannot write data
   or read application tables.
"""

import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlglot
from opentelemetry import trace
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlglot import exp

from app.analytics.schema import ALLOWED_TABLES, READER_ROLE, SCHEMA

tracer = trace.get_tracer("app.analytics")

# Functions a query may call. Typed sqlglot expressions are matched by class name, others
# (exp.Anonymous) by SQL name. Anything else — pg_sleep, set_config, dblink, pg_read_file,
# lo_import, current_setting... — is rejected.
ALLOWED_FUNCTIONS = frozenset(
    {
        # aggregates
        "count", "sum", "avg", "min", "max", "stddev", "stddev_samp", "stddev_pop",
        "variance", "percentilecont", "percentiledisc", "median", "countif", "bool_and",
        "bool_or", "array_agg", "string_agg", "grouptoarray", "groupconcat", "arrayagg",
        "logicaland", "logicalor", "filter", "within_group", "withingroup",
        # window
        "rownumber", "row_number", "rank", "dense_rank", "denserank", "ntile", "lag", "lead",
        "first_value", "firstvalue", "last_value", "lastvalue", "percent_rank", "cume_dist",
        # dates
        "date_trunc", "datetrunc", "timestamptrunc", "extract", "date_part", "datepart",
        "age", "now", "currenttimestamp", "current_timestamp", "currentdate", "current_date",
        "to_char", "tochar", "date", "todate", "to_date", "make_date", "makeinterval",
        "dateadd", "datesub", "datediff", "timestampadd", "timestampsub", "timestampdiff",
        "tsordstodate", "tsordstotime", "tsordstotimestamp", "strtotime", "timetostr",
        "unixtotime", "timetounix", "generate_series", "generateseries", "gendaterange",
        "generatedatearray", "interval", "dayofweek", "dayofmonth", "dayofyear", "weekofyear",
        "year", "month", "day", "week", "quarter", "hour", "minute", "second",
        # math
        "round", "floor", "ceil", "abs", "power", "pow", "sqrt", "ln", "log", "exp", "mod",
        "greatest", "least", "sign", "div", "safedivide", "nullif", "coalesce", "if", "case",
        "cast", "trycast", "width_bucket", "exists", "explodinggenerateseries",
        # text
        "lower", "upper", "length", "trim", "concat", "concatws", "substring", "left",
        "right", "replace", "initcap", "lpad", "rpad", "split_part", "splitpart", "position",
        "strposition", "regexplike", "anyvalue",
    }
)  # fmt: skip

STATEMENT_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)


class SQLGuardError(ValueError):
    """The query is not allowed. The message is safe to show to the model and the user."""


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str  # normalized, with the enforced LIMIT
    tables: list[str]


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return type(node).__name__.lower()


def validate_sql(sql: str, *, max_rows: int) -> ValidatedQuery:
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise SQLGuardError(f"Could not parse the query: {str(exc).splitlines()[0]}") from exc
    if len(statements) != 1:
        raise SQLGuardError("Exactly one statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, STATEMENT_TYPES):
        raise SQLGuardError(f"Only SELECT queries are allowed, not {tree.key.upper()}.")

    # Writes can hide inside a SELECT (data-modifying CTEs, SELECT ... INTO, FOR UPDATE).
    for node in tree.walk():
        if isinstance(node, exp.Insert | exp.Update | exp.Delete | exp.Merge | exp.Create
                      | exp.Drop | exp.Alter | exp.Command | exp.Into | exp.Lock):  # fmt: skip
            raise SQLGuardError("The query must be read-only.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables: list[str] = []
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        schema = (table.db or "").lower()
        if not schema and name in cte_names:
            continue
        if isinstance(table.this, exp.Func):  # e.g. FROM generate_series(...)
            continue
        if schema != SCHEMA or name not in ALLOWED_TABLES:
            qualified = f"{schema}.{name}" if schema else name
            raise SQLGuardError(
                f"Table {qualified} is not allowed. Use only: "
                + ", ".join(f"{SCHEMA}.{t}" for t in sorted(ALLOWED_TABLES))
            )
        if table.catalog:
            raise SQLGuardError("Cross-database references are not allowed.")
        if f"{schema}.{name}" not in tables:
            tables.append(f"{schema}.{name}")
    if not tables:
        raise SQLGuardError("The query must read at least one analytics table.")

    for func in tree.find_all(exp.Func):
        if isinstance(func, exp.Binary | exp.Connector | exp.Unary):  # AND, OR, NOT, ...
            continue
        name = _function_name(func)
        if name not in ALLOWED_FUNCTIONS:
            raise SQLGuardError(f"Function {name} is not allowed.")

    limit = tree.args.get("limit")
    current = None
    if isinstance(limit, exp.Limit) and isinstance(limit.expression, exp.Literal):
        current = int(limit.expression.this) if limit.expression.is_int else None
    if current is None or current > max_rows:
        tree = (
            tree.limit(max_rows, copy=False)
            if isinstance(tree, exp.Select)
            else (exp.select("*").from_(tree.subquery("q")).limit(max_rows))
        )
    return ValidatedQuery(sql=tree.sql(dialect="postgres"), tables=tables)


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]  # JSON-safe values
    truncated: bool
    elapsed_ms: int


class SQLExecutionError(RuntimeError):
    """The database rejected or aborted the query. The message is safe to show."""


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, int | float | str | bool) or value is None:
        return value
    return str(value)


class SQLExecutor:
    def __init__(self, engine: AsyncEngine, *, timeout_ms: int, max_rows: int) -> None:
        self.engine = engine
        self.timeout_ms = timeout_ms
        self.max_rows = max_rows

    async def run(self, sql: str) -> QueryResult:
        """Execute an already validated query with least privilege. Never commits."""
        with tracer.start_as_current_span(
            "sql.execute", attributes={"db.system": "postgresql"}
        ) as span:
            result = await self._run(sql)
            span.set_attribute("db.response.returned_rows", len(result.rows))
            return result

    async def _run(self, sql: str) -> QueryResult:
        started = time.perf_counter()
        async with self.engine.connect() as conn:
            try:
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                await conn.execute(text(f"SET LOCAL ROLE {READER_ROLE}"))
                await conn.execute(text(f"SET LOCAL statement_timeout = {int(self.timeout_ms)}"))
                result = await conn.execute(text(sql))
                columns = list(result.keys())
                fetched = result.fetchmany(self.max_rows + 1)
            except DBAPIError as exc:
                raise SQLExecutionError(_db_error_message(exc)) from exc
            finally:
                await conn.rollback()
        rows = [[_json_safe(v) for v in row] for row in fetched[: self.max_rows]]
        return QueryResult(
            columns=columns,
            rows=rows,
            truncated=len(fetched) > self.max_rows,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )


def _db_error_message(exc: DBAPIError) -> str:
    original = getattr(exc, "orig", None) or exc
    message = str(original).strip().splitlines()[0] if str(original).strip() else ""
    if "canceling statement due to statement timeout" in message:
        return "The query took too long and was cancelled. Aggregate more or filter by date."
    # asyncpg errors look like "<class '...'>: message"; keep only the message.
    return message.split(": ", 1)[-1][:300] or type(original).__name__
