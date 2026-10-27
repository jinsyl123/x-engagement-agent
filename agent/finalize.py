"""Turn the agent's raw session file into a reviewable output, or refuse to.

Order matters:
  1. Schema: every post must parse (see schemas.py). One bad post fails the run.
  2. Accounting: engaged + skipped must equal posts_analyzed. A mismatch means
     the agent dropped or invented posts, so nothing it wrote can be trusted.
  3. Re-check against state: the agent was *told* to run skip_filter on every
     post, but agents don't always follow instructions. Re-apply the
     dedup/author rules here, in code, against the state on disk.
  4. Write output + update state + render the PR body for human review.

Usage: python -m agent.finalize session-output.json [--publish]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from .config import load_rules
from .schemas import EngagePost, Session, SkippedPost
from .state import State, StateError


class SessionError(RuntimeError):
    pass


def load_session(path: str | Path) -> Session:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SessionError(f"Can't read session file: {e}") from e
    try:
        return Session.model_validate(raw)
    except ValidationError as e:
        raise SessionError(f"Session failed schema validation:\n{e}") from e


def check_accounting(session: Session) -> None:
    analyzed = session.summary.posts_analyzed
    found = len(session.engage_posts) + len(session.skipped_posts)
    if analyzed != found:
        raise SessionError(
            f"Accounting mismatch: summary says {analyzed} analyzed, found {found} "
            f"({len(session.engage_posts)} engage + {len(session.skipped_posts)} skipped)."
        )


def recheck_against_state(session: Session, state: State, max_per_window: int,
                          window_days: int, now: datetime, min_score: int = 0) -> list[str]:
    """Move posts that slipped past the agent's skip step into skipped_posts.
    Returns a note per moved post so the reviewer can see the agent erred."""
    cutoff = now - timedelta(days=window_days)
    kept, notes = [], []
    batch_counts: dict[str, int] = {}
    for post in session.engage_posts:
        handle = state.handle(post.author)
        prior = sum(dt > cutoff for dt in state.engagements(post.author))
        reason = None
        if post.score.score < min_score:
            reason = f"Score {post.score.score} below {min_score} (caught at finalize)"
        elif not post.reply.reasoning.bridge_test.decision:
            reason = "Bridge test failed but post was proposed (caught at finalize)"
        elif post.link in state.seen:
            reason = "Already seen (caught at finalize)"
        elif prior + batch_counts.get(handle, 0) >= max_per_window:
            reason = "Author over-engaged (caught at finalize)"
        elif batch_counts.get(handle):
            reason = "Second post by same author in one session (caught at finalize)"
        if reason:
            session.skipped_posts.append(SkippedPost(link=post.link, author=post.author, reason=reason))
            notes.append(f"{post.link}: {reason}")
            continue
        batch_counts[handle] = batch_counts.get(handle, 0) + 1
        kept.append(post)
    session.engage_posts = kept
    return notes


def render_pr_body(session: Session, ts: str, notes: list[str]) -> str:
    lines = [
        f"## Engagement session {ts}",
        "",
        f"Analyzed **{session.summary.posts_analyzed}** · "
        f"proposing **{len(session.engage_posts)}** · skipped **{len(session.skipped_posts)}**",
        "",
        "For each post, set **Decision** to `accept` or `reject` (with a reason). "
        "Edit the reply text inline if needed; the review-sync step treats this body as the source of truth.",
    ]
    if notes:
        lines += ["", "> ⚠️ Finalize caught posts the agent should have skipped:"]
        lines += [f"> - {n}" for n in notes]
    for i, p in enumerate(session.engage_posts, 1):
        r = p.reply
        lines += [
            "", "---", "",
            f"### {i}. {p.author} · score {p.score.score}/10",
            f"[post]({p.link}) · prior engagements: {p.prior_engagements}",
            "", f"> {p.excerpt}", "",
            f"**Why engage:** {p.score.reasoning}",
            f"**Bridge:** {r.reasoning.bridge_test.connection_point} ({r.reasoning.bridge_test.strength})",
            "", "**Suggested reply:**", "", f"```\n{r.chosen_reply}\n```",
            f"Mentions product: {'yes' if r.brand_mention.mentions_product else 'no'} · {r.brand_mention.reasoning}",
            "", "**Decision:** accept / reject",
        ]
    return "\n".join(lines) + "\n"


def finalize(session_path: str | Path, out_root: str | Path = ".", config: str = "config.toml",
             now: datetime | None = None, publish=None) -> dict:
    """publish: optional callable(output_file, body_file). State is saved only
    after it succeeds, so a failed push can be retried without the posts
    being marked as already seen."""
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rules = load_rules(config)
    out_root = Path(out_root)
    state = State(out_root / "state")       # raises StateError if corrupt
    state.prune(now, rules.window_days)

    session = load_session(session_path)
    check_accounting(session)
    notes = recheck_against_state(session, state, rules.max_author_engagements, rules.window_days, now,
                                  rules.min_score)

    day_dir = out_root / "outputs" / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stem = now.strftime("%H%M%S")
    out_file = day_dir / f"{stem}.json"
    body_file = day_dir / f"{stem}.pr.md"
    out_file.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    body_file.write_text(render_pr_body(session, ts, notes), encoding="utf-8")

    if publish and session.engage_posts:
        publish(str(out_file), str(body_file))

    # Record engagements at proposal time, not after review: even a rejected
    # reply means a human looked at that post, and it shouldn't come back.
    for p in session.engage_posts:
        state.record(p.link, p.author, ts)
    state.save()

    return {"output": str(out_file), "pr_body": str(body_file),
            "engage": len(session.engage_posts), "skipped": len(session.skipped_posts),
            "caught_at_finalize": len(notes)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_file")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--publish", action="store_true", help="open a PR for review")
    args = ap.parse_args()
    publish = None
    if args.publish:
        from .publish import open_pr
        publish = open_pr
    try:
        result = finalize(args.session_file, config=args.config, publish=publish)
    except (SessionError, StateError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
