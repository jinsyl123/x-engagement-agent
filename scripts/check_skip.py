#!/usr/bin/env python3
"""Cheap, deterministic filter that runs before any LLM call.

Every post the browser agent finds goes through here first. Rules only catch
the obvious cases (blocked topics, crowded or stale threads, authors we've
engaged recently). Anything nuanced is left to the LLM.

Read-only: it never records engagements. Only output_pr writes memory.

Usage from an agent:  echo '<post json>' | ./run.sh -m scripts.check_skip
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config_loader import ConfigError, Rules, load_rules
from .state import State, StateError, parse_ts


@dataclass
class Decision:
    keep: bool
    reason: str = ""
    engagements: int = 0

    def to_json(self) -> str:
        if self.keep:
            return json.dumps({"status": "keep", "engagements": self.engagements})
        return json.dumps({"status": "skip", "reason": self.reason})


def check(post: dict, state: State, rules: Rules, now: datetime) -> Decision:
    link, author = post.get("link"), post.get("author")
    if not (isinstance(link, str) and link.strip() and isinstance(author, str) and author.strip()):
        return Decision(False, "Invalid or incomplete JSON: 'link' and 'author' are required")

    # 0) Blocked keywords. Word boundaries: "election" must not match "natural selection".
    text = f"{post.get('content') or ''} {author}".lower()
    for kw in sorted(rules.blocked_keywords):
        if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text):
            return Decision(False, f"Blocked keyword: {kw}")

    # 0.5) High competition
    try:
        replies = int(post.get("reply_count"))
    except (TypeError, ValueError):
        replies = None
    if replies is not None and replies > rules.max_reply_count:
        return Decision(False, f"High competition: {replies} replies")

    # 0.6) Post age
    posted = parse_ts(post.get("timestamp") or "")
    if posted and now - posted > timedelta(hours=rules.max_post_age_hours):
        return Decision(False, f"Post too old (>{rules.max_post_age_hours}h)")

    # 1) Seen before
    if link in state.seen_links:
        return Decision(False, "Post seen before")

    # 2) Author: not today, not yesterday, not more than N times in the window
    history = state.engagements(author)
    days_since = {(now.date() - dt.date()).days for dt in history}
    if 0 in days_since:
        return Decision(False, "Already engaged with author today")
    if 1 in days_since:
        return Decision(False, "Engaged with author yesterday")

    recent = [dt for dt in history if dt > now - timedelta(days=rules.window_days)]
    if len(recent) >= rules.max_author_engagements:
        return Decision(False, f"Author has been engaged with {len(recent)} times in the last {rules.window_days} days")

    return Decision(True, engagements=len(recent))


def main() -> int:
    try:
        rules = load_rules()
        state = State()
    except (ConfigError, StateError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc)
    state.prune(now, rules.window_days)
    try:
        post = json.load(sys.stdin)
    except json.JSONDecodeError:
        post = {}
    # Always print a decision and exit 0 for bad posts: the calling agent reads
    # stdout, and a non-zero exit tends to make agents improvise instead of skipping.
    print(check(post if isinstance(post, dict) else {}, state, rules, now).to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
