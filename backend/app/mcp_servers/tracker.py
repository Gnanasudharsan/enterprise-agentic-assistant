"""Issue-tracker MCP server: the assistant's one integration with an external system.

Runs as its own process (stdio transport) and holds the only tracker credentials. The
assistant's backend sees tool schemas and results, never the token, and the model never
sees either. Two backends:

- local (default): a SQLite issue tracker, for demos, tests, and CI. Keys look like HEL-12.
- github: GitHub Issues for one repository (GITHUB_REPO="owner/name"). Use a fine-grained
  token scoped to that repository with only "Issues: read and write".

    python -m app.mcp_servers.tracker          # serve over stdio
"""

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol

import httpx2
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

Label = Literal["onboarding", "verification", "support", "incident-follow-up", "bug", "docs"]
Priority = Literal["P1", "P2", "P3", "P4"]


class Issue(BaseModel):
    key: str  # "HEL-12" (local) or "#42" (GitHub)
    title: str
    url: str
    state: str
    labels: list[str] = []
    created_at: str


class IssueList(BaseModel):
    issues: list[Issue]


class Tracker(Protocol):
    name: str

    def create(self, title: str, body: str, labels: list[str]) -> Issue: ...

    def search(self, query: str, limit: int) -> list[Issue]: ...


class LocalTracker:
    name = "local"

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS issues (n INTEGER PRIMARY KEY AUTOINCREMENT, "
            "title TEXT NOT NULL, body TEXT NOT NULL, labels TEXT NOT NULL, "
            "state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL)"
        )
        self._db.commit()

    @staticmethod
    def _issue(row: tuple) -> Issue:
        n, title, labels, state, created = row
        return Issue(
            key=f"HEL-{n}",
            title=title,
            url=f"tracker://helio/HEL-{n}",
            state=state,
            labels=[label for label in labels.split(",") if label],
            created_at=created,
        )

    def create(self, title: str, body: str, labels: list[str]) -> Issue:
        created = datetime.now(UTC).isoformat(timespec="seconds")
        cur = self._db.execute(
            "INSERT INTO issues (title, body, labels, created_at) VALUES (?, ?, ?, ?)",
            (title, body, ",".join(labels), created),
        )
        self._db.commit()
        return self._issue((cur.lastrowid, title, ",".join(labels), "open", created))

    def search(self, query: str, limit: int) -> list[Issue]:
        words = [w for w in query.lower().split() if len(w) > 2][:8]
        rows = self._db.execute(
            "SELECT n, title, body, labels, state, created_at FROM issues ORDER BY n DESC"
        ).fetchall()
        # Keyword overlap, title words counting double; a match needs a real overlap, not
        # one shared word.
        needed = max(2, round(0.4 * len(words)))
        scored = []
        for n, title, body, labels, state, created in rows:
            score = sum(2 * (w in title.lower()) + (w in body.lower()) for w in words)
            if score >= 2 * needed:
                scored.append((score, (n, title, labels, state, created)))
        scored.sort(key=lambda s: -s[0])
        return [self._issue(row) for _, row in scored[:limit]]


class GitHubTracker:
    name = "github"

    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self._http = httpx2.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )

    @staticmethod
    def _issue(data: dict) -> Issue:
        return Issue(
            key=f"#{data['number']}",
            title=data["title"],
            url=data["html_url"],
            state=data["state"],
            labels=[label["name"] for label in data.get("labels", [])],
            created_at=data["created_at"],
        )

    def create(self, title: str, body: str, labels: list[str]) -> Issue:
        resp = self._http.post(
            f"/repos/{self.repo}/issues", json={"title": title, "body": body, "labels": labels}
        )
        resp.raise_for_status()
        return self._issue(resp.json())

    def search(self, query: str, limit: int) -> list[Issue]:
        q = f"{query} repo:{self.repo} is:issue"
        resp = self._http.get("/search/issues", params={"q": q, "per_page": limit})
        resp.raise_for_status()
        return [self._issue(item) for item in resp.json().get("items", [])]


def tracker_from_env() -> Tracker:
    if os.getenv("TRACKER_BACKEND", "local") == "github":
        repo, token = os.getenv("GITHUB_REPO"), os.getenv("GITHUB_TOKEN")
        if not repo or not token:
            raise SystemExit("TRACKER_BACKEND=github needs GITHUB_REPO and GITHUB_TOKEN")
        return GitHubTracker(repo, token)
    return LocalTracker(os.getenv("TRACKER_DB_PATH", "data/tracker.sqlite3"))


def build_server(tracker: Tracker) -> MCPServer:
    server = MCPServer(
        name="helio-tracker",
        instructions=f"Helio's issue tracker ({tracker.name} backend).",
    )

    @server.tool(
        title="Create issue",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False
        ),
    )
    def create_issue(
        title: Annotated[str, Field(min_length=8, max_length=120, description="Concise summary")],
        body: Annotated[
            str,
            Field(
                min_length=20,
                max_length=6000,
                description="Markdown: context, evidence, next steps",
            ),
        ],
        labels: Annotated[list[Label], Field(max_length=4)] = [],  # noqa: B006
        priority: Priority = "P3",
    ) -> Issue:
        """Create a new issue in Helio's tracker."""
        return tracker.create(title, body, [*dict.fromkeys(labels), f"priority:{priority}"])

    @server.tool(title="Search issues", annotations=ToolAnnotations(readOnlyHint=True))
    def search_issues(
        query: Annotated[str, Field(min_length=2, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=10)] = 5,
    ) -> IssueList:
        """Search existing issues (to avoid duplicates)."""
        return IssueList(issues=tracker.search(query, limit))

    return server


if __name__ == "__main__":
    build_server(tracker_from_env()).run("stdio")
