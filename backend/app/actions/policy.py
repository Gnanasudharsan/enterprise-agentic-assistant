"""Action policy, enforced by the backend whatever the model says.

- Allow-list: a tool can be used only if it is configured, and only by its listed groups.
- Approval: every tool that is not known to be read-only needs a recorded human approval.
  The server's own read-only annotation is not trusted for this.
- Integrity: approvals are bound to a hash of the exact arguments that were approved.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Tools the backend has reviewed as side-effect free. Anything else requires approval.
READ_ONLY_TOOLS = frozenset({"search_issues"})


class PermissionDenied(Exception):
    """The caller may not use this tool. The message is safe to show."""


@dataclass(frozen=True)
class ActionPolicy:
    permissions: dict[str, frozenset[str]]

    @classmethod
    def from_settings(cls, permissions: dict[str, list[str]]) -> "ActionPolicy":
        return cls({tool: frozenset(groups) for tool, groups in permissions.items()})

    def can_use(self, tool: str, groups: Iterable[str]) -> bool:
        return bool(self.permissions.get(tool, frozenset()) & set(groups))

    def check(self, tool: str, groups: Iterable[str]) -> None:
        if tool not in self.permissions:
            raise PermissionDenied(f"The tool {tool!r} is not enabled.")
        if not self.can_use(tool, groups):
            raise PermissionDenied(f"Your access groups do not allow {tool!r}.")

    @staticmethod
    def requires_approval(tool: str) -> bool:
        return tool not in READ_ONLY_TOOLS


def args_hash(tool: str, arguments: dict[str, Any]) -> str:
    canonical = json.dumps({"tool": tool, "arguments": arguments}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
