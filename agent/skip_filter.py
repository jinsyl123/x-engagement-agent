"""Cheap, deterministic filter that runs before any LLM call.

Every post the browser agent finds goes through here first. Rules only catch
the obvious cases (blocked topics, crowded or stale threads, authors we've
engaged recently). Anything nuanced is left to the LLM, which is slower,
costs money, and is non-deterministic.

Usage from an agent:  echo '<post json>' | python -m agent.skip_filter
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import Rules, load_rules
from .state import State, parse_ts


@dataclass
class Decision:
    keep: bool
    reason: str = ""
    prior_engagements: int = 0

    def to_json(self) -> str:
        if self.keep:
            return json.dumps({"status": "keep", "engagements": self.prior_engagements})
        return json.dumps({"status": "skip", "reason": self.reason})


def check(post: dict, state: State, rules: Rules, now: datetime) -> Decision:
    link, author = post.get("link"), post.get("author")
    if not (isinstance(link, str) and link.strip() and isinstance(author, str) and author.strip()):
        return Decision(False, "Malformed post: 'link' and 'author' are required")

    text = f"{post.get('content') or ''} {author}".lower()
    for kw in sorted(rules.blocked_keywords):
        if kw in text:
            return Decision(False, f"Blocked keyword: {kw}")

    try:
        replies = int(post.get("reply_count"))
    except (TypeError, ValueError):
        replies = None
    if replies is not None and replies > rules.max_reply_count:
        return Decision(False, f"Crowded thread: {replies} replies")

    posted = parse_ts(post.get("timestamp") or "")
    if posted and now - posted > timedelta(hours=rules.max_post_age_hours):
        return Decision(False, f"Stale post (>{rules.max_post_age_hours}h)")

    if link in state.seen:
        return Decision(False, "Seen in a previous session")

    history = state.engagements(author)
    if history and (now.date() - history[-1].date()).days <= rules.author_cooldown_days:
        return Decision(False, "Engaged this author too recently")

    recent = [dt for dt in history if dt > now - timedelta(days=rules.window_days)]
    if len(recent) >= rules.max_author_engagements:
        return Decision(False, f"Author engaged {len(recent)}x in {rules.window_days} days")

    return Decision(True, prior_engagements=len(recent))


def main() -> int:
    rules = load_rules(sys.argv[1] if len(sys.argv) > 1 else "config.toml")
    state = State("state")
    now = datetime.now(timezone.utc)
    state.prune(now, rules.window_days)
    try:
        post = json.load(sys.stdin)
    except json.JSONDecodeError:
        post = {}
    # Always print a decision and exit 0: the calling agent reads stdout,
    # and a non-zero exit tends to make agents improvise instead of skipping.
    print(check(post if isinstance(post, dict) else {}, state, rules, now).to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
