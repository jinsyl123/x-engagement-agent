from datetime import datetime, timedelta, timezone

import pytest

from agent.state import State, StateError

NOW = datetime(2026, 1, 15, tzinfo=timezone.utc)


def test_corrupt_state_fails_loudly(tmp_path):
    (tmp_path / "seen_posts.json").write_text("{not json")
    with pytest.raises(StateError):
        State(tmp_path)


def test_wrong_shape_fails_loudly(tmp_path):
    (tmp_path / "seen_posts.json").write_text("[]")
    with pytest.raises(StateError):
        State(tmp_path)


def test_prune_drops_old_and_empty_authors(tmp_path):
    s = State(tmp_path)
    s.record("old", "@x", (NOW - timedelta(days=8)).isoformat())
    s.record("new", "@y", (NOW - timedelta(days=1)).isoformat())
    s.prune(NOW, 7)
    assert list(s.seen) == ["new"] and list(s.authors) == ["y"]


def test_round_trip_leaves_no_tmp_files(tmp_path):
    s = State(tmp_path)
    s.record("l", "@z", NOW.isoformat())
    s.save()
    assert State(tmp_path).seen == {"l": NOW.isoformat()}
    assert not list(tmp_path.glob("*.tmp"))
