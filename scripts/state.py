"""Memory between sessions, in the same two files as the original:

  seen_posts.json        [{"link": ..., "timestamp": ...}, ...]
  engagement_cache.json  {"author": ["timestamp", ...], ...}

Two rules (both were gaps in the original):
  1. A corrupt state file stops the run. Silently resetting to empty would
     make the agent forget everything and re-engage old posts and authors.
  2. Writes are atomic (tmp file + os.replace), so a crash mid-write can't
     produce the corrupt file that rule 1 would then trip on.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEEN_POSTS_FILE = "seen_posts.json"
ENGAGEMENT_CACHE_FILE = "engagement_cache.json"


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
    def __init__(self, state_dir: str | Path = "."):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seen_path = self.dir / SEEN_POSTS_FILE
        self.cache_path = self.dir / ENGAGEMENT_CACHE_FILE
        self.seen_posts: list = _read(self.seen_path, list)
        self.engagement_cache: dict = _read(self.cache_path, dict)

    @property
    def seen_links(self) -> set:
        return {p.get("link") for p in self.seen_posts if isinstance(p, dict)}

    @staticmethod
    def handle(author: str) -> str:
        return author.strip().lstrip("@").lower()

    def prune(self, now: datetime, window_days: int) -> None:
        """Drop memory older than the window so state can't grow forever.
        In memory only: nothing is written until save()."""
        cutoff = now - timedelta(days=window_days)

        def fresh(ts):
            dt = parse_ts(ts) if isinstance(ts, str) else None
            return dt is not None and dt > cutoff

        self.seen_posts = [p for p in self.seen_posts if isinstance(p, dict) and fresh(p.get("timestamp"))]
        self.engagement_cache = {
            a: kept for a, stamps in self.engagement_cache.items()
            if (kept := [ts for ts in stamps if fresh(ts)])
        }

    def engagements(self, author: str) -> list[datetime]:
        stamps = (parse_ts(ts) for ts in self.engagement_cache.get(self.handle(author), []))
        return sorted(dt for dt in stamps if dt is not None)

    def record(self, link: str, author: str, ts: str) -> None:
        if link not in self.seen_links:
            self.seen_posts.append({"link": link, "timestamp": ts})
        stamps = self.engagement_cache.setdefault(self.handle(author), [])
        if ts not in stamps:
            stamps.append(ts)

    def save(self) -> None:
        _write_atomic(self.seen_path, self.seen_posts)
        _write_atomic(self.cache_path, self.engagement_cache)
