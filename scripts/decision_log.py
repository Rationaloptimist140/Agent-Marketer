"""Append-only decision log for every automated marketing action.

Each record answers: what was proposed, why, from which inputs, who approved it,
and what happened. Records are JSON Lines so they can be grepped, diffed and
loaded into a report without a database.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path("logs/decisions.jsonl")
VALID_STATUSES = {"proposed", "approved", "rejected", "executed", "failed"}


@dataclass(frozen=True)
class Decision:
    pillar: str
    action: str
    target: str
    reasoning: str
    status: str = "proposed"
    brand: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = True
    approved_by: str | None = None
    outcome: str | None = None
    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid status {self.status!r}; expected one of {sorted(VALID_STATUSES)}")
        if self.status == "executed" and self.requires_approval and not self.approved_by:
            raise ValueError("an action that requires approval cannot be executed without approved_by")


def append(decision: Decision, path: Path = DEFAULT_LOG_PATH) -> Decision:
    """Append one decision. The log is never rewritten, only extended."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(decision), sort_keys=True, ensure_ascii=False) + "\n")
    return decision


def read(path: Path = DEFAULT_LOG_PATH) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
