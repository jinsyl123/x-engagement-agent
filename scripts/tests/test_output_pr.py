import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.output_pr import SessionError, process_session_data
from scripts.state import State

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "session-output.json"
NOW = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)


def run(workdir, data=None, **kw):
    path = workdir / "session-output.json"
    if data is None:
        shutil.copy(EXAMPLE, path)
    else:
        path.write_text(json.dumps(data))
    return process_session_data(path, root=workdir, config=workdir / "config" / "config.toml", now=NOW, **kw)


def example():
    return json.loads(EXAMPLE.read_text())


def test_happy_path_writes_output_skipped_log_pr_body_and_state(workdir):
    r = run(workdir)
    assert r["engage"] == 1 and r["skipped"] == 2 and r["caught_at_output_pr"] == 0
    assert Path(r["output"]).name == "2026-01-15-093000.json"
    assert (workdir / "logs" / "2026-01-15" / "093000.skipped.json").exists()
    assert "**Decision:** accept / reject" in Path(r["pr_body"]).read_text()
    assert "https://x.com/example_dev/status/1000000000000000001" in State(workdir).seen_links


def test_accounting_mismatch_fails(workdir):
    data = example()
    data["summary"]["posts_analyzed"] = 5
    with pytest.raises(SessionError, match="Sanity Check Failed"):
        run(workdir, data)


def test_schema_violation_fails(workdir):
    data = example()
    data["engage_posts"][0]["analysis"]["score"] = 42
    with pytest.raises(SessionError, match="schema"):
        run(workdir, data)


def test_reply_over_280_chars_fails(workdir):
    data = example()
    data["engage_posts"][0]["reply_generation"]["chosen_reply"] = "x" * 281
    with pytest.raises(SessionError):
        run(workdir, data)


def test_second_run_catches_post_the_agent_should_have_skipped(workdir):
    run(workdir)
    r = run(workdir)  # agent "forgot" to run check_skip and re-proposed the same post
    assert r["engage"] == 0 and r["caught_at_output_pr"] == 1


def test_two_posts_same_author_in_one_session(workdir):
    data = example()
    dup = json.loads(json.dumps(data["engage_posts"][0]))
    dup["link"] = "https://x.com/example_dev/status/1000000000000000009"
    data["engage_posts"].append(dup)
    data["summary"]["posts_analyzed"] = 4
    r = run(workdir, data)
    assert r["engage"] == 1 and r["caught_at_output_pr"] == 1


def test_low_score_is_dropped_in_code(workdir):
    data = example()
    data["engage_posts"][0]["analysis"]["score"] = 5
    r = run(workdir, data)
    assert r["engage"] == 0 and r["caught_at_output_pr"] == 1


def test_failed_bridge_is_dropped_in_code(workdir):
    data = example()
    data["engage_posts"][0]["reply_generation"]["internal_monologue"]["bridge_test_analysis"]["decision"] = False
    assert run(workdir, data)["engage"] == 0


def test_failed_publish_does_not_mark_posts_seen(workdir):
    def boom(*_):
        raise RuntimeError("push failed")

    with pytest.raises(RuntimeError):
        run(workdir, finalize=True, publish=boom)
    assert State(workdir).seen_posts == []
    assert run(workdir)["engage"] == 1  # retry still works
