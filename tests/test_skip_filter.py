from datetime import datetime, timedelta, timezone

from agent.config import load_rules
from agent.skip_filter import check
from agent.state import State

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def post(**kw):
    base = {"link": "https://x.com/a/status/1", "author": "@a", "content": "agents and retries",
            "reply_count": 5, "timestamp": (NOW - timedelta(hours=2)).isoformat()}
    return {**base, **kw}


def setup(workdir):
    return State(workdir / "state"), load_rules(workdir / "config.toml")


def test_keeps_a_normal_post(workdir):
    state, rules = setup(workdir)
    assert check(post(), state, rules, NOW).keep


def test_rejects_malformed(workdir):
    state, rules = setup(workdir)
    assert not check({"link": "x"}, state, rules, NOW).keep


def test_blocked_keyword_case_insensitive(workdir):
    state, rules = setup(workdir)
    d = check(post(content="Switched from Competitor-A today"), state, rules, NOW)
    assert not d.keep and "competitor-a" in d.reason


def test_crowded_and_stale(workdir):
    state, rules = setup(workdir)
    assert not check(post(reply_count=301), state, rules, NOW).keep
    assert not check(post(timestamp=(NOW - timedelta(hours=49)).isoformat()), state, rules, NOW).keep


def test_garbage_reply_count_is_ignored_not_fatal(workdir):
    state, rules = setup(workdir)
    assert check(post(reply_count="1.2K"), state, rules, NOW).keep


def test_seen_post(workdir):
    state, rules = setup(workdir)
    state.record("https://x.com/a/status/1", "@b", (NOW - timedelta(days=3)).isoformat())
    assert not check(post(), state, rules, NOW).keep


def test_author_cooldown_and_handle_normalisation(workdir):
    state, rules = setup(workdir)
    state.record("https://x.com/a/status/0", "A", (NOW - timedelta(days=1)).isoformat())
    d = check(post(author="@a"), state, rules, NOW)
    assert not d.keep and "recently" in d.reason


def test_author_window_cap(workdir):
    state, rules = setup(workdir)
    for i, days in enumerate([2, 4, 6]):
        state.record(f"https://x.com/a/status/9{i}", "@a", (NOW - timedelta(days=days)).isoformat())
    assert not check(post(), state, rules, NOW).keep
