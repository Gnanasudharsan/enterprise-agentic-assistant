"""Logging setup: readable text locally, one JSON object per line in production.

The JSON fields follow Cloud Logging's conventions (`severity`, `message`, and the trace
id of the current OpenTelemetry span), so logs group under their request's trace.
"""

import json
import logging
import os
import time

from fastapi import FastAPI, Request
from opentelemetry import trace

from app.core.config import Settings

access_logger = logging.getLogger("app.access")


class JsonFormatter(logging.Formatter):
    def __init__(self, project: str | None = None) -> None:
        super().__init__()
        self.project = project

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if extra := getattr(record, "fields", None):
            entry.update(extra)
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            trace_id = f"{ctx.trace_id:032x}"
            entry["logging.googleapis.com/trace"] = (
                f"projects/{self.project}/traces/{trace_id}" if self.project else trace_id
            )
            entry["logging.googleapis.com/spanId"] = f"{ctx.span_id:016x}"
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler()
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter(os.getenv("GOOGLE_CLOUD_PROJECT")))
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.handlers[:] = [handler]


def install_access_log(app: FastAPI) -> None:
    """One structured line per request (uvicorn's access log is turned off in production)."""

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        if not request.url.path.startswith("/health"):
            access_logger.info(
                "%s %s %s", request.method, request.url.path, response.status_code,
                extra={"fields": {"httpRequest": {
                    "requestMethod": request.method,
                    "requestUrl": request.url.path,
                    "status": response.status_code,
                    "latency": f"{time.perf_counter() - started:.3f}s",
                }}},
            )  # fmt: skip
        return response
