"""Load filter rules from TOML. Keywords live in config, not code, so the
same pipeline works for any product without a code change."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass(frozen=True)
class Rules:
    blocked_keywords: frozenset = field(default_factory=frozenset)
    max_reply_count: int = 300          # crowded thread: our reply gets buried
    max_post_age_hours: int = 48        # stale thread: nobody reads new replies
    author_cooldown_days: int = 1       # no engaging the same person two days running
    max_author_engagements: int = 3     # ...or more than N times per window
    window_days: int = 7                # also the TTL for seen-post memory


def load_rules(path: str | Path) -> Rules:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    filters = raw.get("filters", {})
    keywords = set()
    for group in filters.get("blocked_keywords", {}).values():
        keywords.update(k.lower() for k in group)
    limits = {k: v for k, v in filters.items() if k != "blocked_keywords"}
    return Rules(blocked_keywords=frozenset(keywords), **limits)
