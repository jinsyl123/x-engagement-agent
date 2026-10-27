"""Memory between sessions: which posts we've seen, and when we last engaged
each author.

Two rules:
  1. A corrupt state file stops the run. Silently resetting to empty would
     make the agent forget everything and re-engage old posts and authors,
     which is the worst failure this system can have in public.
  2. Writes are atomic (tmp file + os.replace), so a crash mid-write can't
     produce the corrupt file that rule 1 would then trip on.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


class StateError(RuntimeError):
    pass


def parse_ts(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _read(path: Path, expected: type):
    if not path.exists() or path.stat().st_size == 0:
        return expected()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise StateError(f"{path} is corrupt ({e}). Fix or delete it before re-running.") from e
    if not isinstance(data, expected):
        raise StateError(f"{path} should hold a {expected.__name__}, got {type(data).__name__}.")
    return data


def _write_atomic(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class State:
    def __init__(self, state_dir: str | Path):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seen_path = self.dir / "seen_posts.json"
        self.authors_path = self.dir / "author_engagements.json"
        self.seen: dict[str, str] = _read(self.seen_path, dict)        # link -> ts
        self.authors: dict[str, list] = _read(self.authors_path, dict)  # handle -> [ts]

    @staticmethod
    def handle(author: str) -> str:
        return author.strip().lstrip("@").lower()

    def prune(self, now: datetime, window_days: int) -> None:
        """Drop memory older than the window so state can't grow forever."""
        cutoff = now - timedelta(days=window_days)

        def fresh(ts):
            dt = parse_ts(ts)
            return dt is not None and dt > cutoff

        self.seen = {link: ts for link, ts in self.seen.items() if fresh(ts)}
        self.authors = {
            a: kept for a, stamps in self.authors.items()
            if (kept := [ts for ts in stamps if fresh(ts)])
        }

    def engagements(self, author: str) -> list[datetime]:
        stamps = (parse_ts(ts) for ts in self.authors.get(self.handle(author), []))
        return sorted(dt for dt in stamps if dt is not None)

    def record(self, link: str, author: str, ts: str) -> None:
        self.seen[link] = ts
        stamps = self.authors.setdefault(self.handle(author), [])
        if ts not in stamps:
            stamps.append(ts)

    def save(self) -> None:
        _write_atomic(self.seen_path, self.seen)
        _write_atomic(self.authors_path, self.authors)
