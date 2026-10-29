#!/usr/bin/env python3
"""Turn the agent's session-output.json into a reviewable PR, or refuse to.

Order matters:
  1. Schema: every post must parse against the models below. One bad post fails the run.
  2. Accounting: engage + skipped must equal posts_analyzed. A mismatch means
     the agent dropped or invented posts, so nothing it wrote can be trusted.
  3. Re-check against state: the agent was *told* to run check_skip on every
     post, but agents don't always follow instructions. Re-apply the rules
     here, in code, and move anything that slipped through to skipped_posts.
  4. Write outputs/ + logs/, open the PR, and only then update memory.

Usage: ./run.sh -m scripts.output_pr --session-data-file session-output.json [--finalize]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from .config_loader import ConfigError, load_github_config, load_rules
from .state import State, StateError

# ── Schema: the contract between the LLM and the rest of the system ──────────
# The fields also force the reasoning order: understand the post (grounding)
# → is there an honest bridge to our domain → brainstorm angles → pick a
# reply → justify any product mention. Skipped thinking shows up in review.


class SkipCheck(BaseModel):
    engagements: int = Field(ge=0)


class Enrichment(BaseModel):
    triggered: bool
    type: Optional[str] = None
    context_added: Optional[str] = None


class GroundingAnalysis(BaseModel):
    post_gist: str = Field(min_length=1)
    author_intent: str
    core_concepts: List[str]


class Analysis(BaseModel):
    reasoning: str
    score: int = Field(ge=1, le=10)


class AlternativeReply(BaseModel):
    reply: str
    strategy: str


class BrandMentionAnalysis(BaseModel):
    mention_product: bool
    reasoning: str


class BridgeTestAnalysis(BaseModel):
    connection_point: str
    bridge_strength: str            # "strong" | "medium" | "weak" | "none"
    decision: bool


class BrainstormedAngle(BaseModel):
    strategy: str
    summary: str


class InternalMonologue(BaseModel):
    assessed_topic: str
    social_intent: str
    bridge_test_analysis: BridgeTestAnalysis
    brainstormed_angles: List[BrainstormedAngle] = Field(min_length=1)


class ReplyGeneration(BaseModel):
    internal_monologue: InternalMonologue
    chosen_reply: str = Field(min_length=1, max_length=280)
    reasoning: str
    alternatives: List[AlternativeReply]
    brand_mention_analysis: BrandMentionAnalysis


class Post(BaseModel):
    link: str
    author: str
    post_content_excerpt: str
    analysis: Analysis
    enrichment: Optional[Enrichment] = None
    grounding_analysis: GroundingAnalysis
    reply_generation: ReplyGeneration
    skip_check: SkipCheck


class SkippedPost(BaseModel):
    link: str
    author: str = ""
    post_content_excerpt: str = ""
    reason: str


class Summary(BaseModel):
    posts_analyzed: int = Field(ge=0)
    engage_posts_count: Optional[int] = None


class Session(BaseModel):
    summary: Summary
    engage_posts: List[Post] = []
    skipped_posts: List[SkippedPost] = []


class SessionError(RuntimeError):
    pass


# ── Validation ────────────────────────────────────────────────────────────────

def load_session(path: str | Path) -> Session:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SessionError(f"Error reading session data file: {e}") from e
    try:
        return Session.model_validate(raw)
    except ValidationError as e:
        raise SessionError(f"A post in session-output.json failed schema validation:\n{e}") from e


def validate_counts(session: Session) -> None:
    analyzed = session.summary.posts_analyzed
    engage, skipped = len(session.engage_posts), len(session.skipped_posts)
    if analyzed != engage + skipped:
        raise SessionError(
            f"Sanity Check Failed: summary says {analyzed} posts analyzed, but found "
            f"{engage + skipped} records (Engage: {engage}, Skipped: {skipped})."
        )


def recheck_against_state(session: Session, state: State, max_per_window: int,
                          window_days: int, now: datetime, min_score: int = 0) -> List[str]:
    """Move posts that slipped past the agent's skip step into skipped_posts.
    Returns a note per moved post so the reviewer can see the agent erred."""
    cutoff = now - timedelta(days=window_days)
    seen = state.seen_links
    kept, notes = [], []
    batch_counts: dict = {}
    for post in session.engage_posts:
        handle = state.handle(post.author)
        prior = sum(dt > cutoff for dt in state.engagements(post.author))
        bridge = post.reply_generation.internal_monologue.bridge_test_analysis
        reason = None
        if post.analysis.score < min_score:
            reason = f"Score {post.analysis.score} below {min_score} (caught at output_pr)"
        elif not bridge.decision:
            reason = "Bridge test failed but post was proposed (caught at output_pr)"
        elif post.link in seen:
            reason = "Post seen before (caught at output_pr)"
        elif prior + batch_counts.get(handle, 0) >= max_per_window:
            reason = "Author over-engaged (caught at output_pr)"
        elif batch_counts.get(handle):
            reason = "Second post by same author in one session (caught at output_pr)"
        if reason:
            session.skipped_posts.append(SkippedPost(
                link=post.link, author=post.author,
                post_content_excerpt=post.post_content_excerpt, reason=reason))
            notes.append(f"{post.link}: {reason}")
            continue
        batch_counts[handle] = batch_counts.get(handle, 0) + 1
        kept.append(post)
    session.engage_posts = kept
    return notes


# ── Output ────────────────────────────────────────────────────────────────────

def get_session_paths(root: Path, ts: datetime):
    """Same layout as the original, with seconds added so two runs in one
    minute can't overwrite each other."""
    stem = ts.strftime("%Y-%m-%d-%H%M%S")
    out_dir = root / "outputs" / ts.strftime("%Y-%m-%d")
    log_dir = root / "logs" / ts.strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{stem}.json", log_dir / f"{ts.strftime('%H%M%S')}.skipped.json", log_dir / f"{ts.strftime('%H%M%S')}.pr.md"


def render_pr_body(session: Session, ts: str, notes: List[str]) -> str:
    lines = [
        f"## Engagement session {ts}",
        "",
        f"Analyzed **{session.summary.posts_analyzed}** · "
        f"proposing **{len(session.engage_posts)}** · skipped **{len(session.skipped_posts)}**",
        "",
        "For each post, set **Decision** to `accept` or `reject` (with a reason). "
        "Edit the reply inline if needed; review-pr treats this body as the source of truth.",
    ]
    if notes:
        lines += ["", "> ⚠️ output_pr caught posts the agent should have skipped:"]
        lines += [f"> - {n}" for n in notes]
    for i, p in enumerate(session.engage_posts, 1):
        rg = p.reply_generation
        bridge = rg.internal_monologue.bridge_test_analysis
        lines += [
            "", "---", "",
            f"### {i}. {p.author} · score {p.analysis.score}/10",
            f"[post]({p.link}) · prior engagements: {p.skip_check.engagements}",
            "", f"> {p.post_content_excerpt}", "",
            f"**Why engage:** {p.analysis.reasoning}",
            f"**Bridge:** {bridge.connection_point} ({bridge.bridge_strength})",
            "", "**Suggested Reply:**", "", f"```\n{rg.chosen_reply}\n```",
            f"Mentions product: {'yes' if rg.brand_mention_analysis.mention_product else 'no'} · "
            f"{rg.brand_mention_analysis.reasoning}",
            "", "**Decision:** accept / reject",
        ]
    return "\n".join(lines) + "\n"


def _run(*cmd: str) -> str:
    # List args, no shell: post text and file names can't be interpreted as commands.
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def publish_pull_request(output_file: str, skipped_file: str, body_file: str, base: str = "main") -> str:
    """One PR per session. Reviewers already live in GitHub; merge history is
    an audit trail of every reply and who approved it. Memory files are
    deliberately NOT committed: they're operator-local, so an unmerged PR
    can't leave main's memory out of date."""
    gh = load_github_config()
    if _run("git", "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Working tree has uncommitted changes; refusing to branch.")
    stem = Path(output_file).stem
    ts = datetime.strptime(stem, "%Y-%m-%d-%H%M%S")
    branch = f"docs/session-analysis-{ts.strftime('%Y-%m-%dT%H%M%SZ')}"
    original = _run("git", "rev-parse", "--abbrev-ref", "HEAD")
    files = [f for f in (output_file, skipped_file) if Path(f).exists()]
    try:
        _run("git", "checkout", "-b", branch, base)
        _run("git", "add", *files)
        _run("git", "commit", "-m", f"docs(session): add {ts.strftime('%Y %m %d %H:%M:%S')} analysis")
        _run("git", "push", "-u", "origin", branch)
        cmd = ["gh", "pr", "create", "--repo", f"{gh.repo_owner}/{gh.repo_name}", "--base", base,
               "--head", branch, "--title", f"Engagement session {stem}", "--body-file", body_file]
        if gh.pr_reviewer:
            cmd += ["--reviewer", gh.pr_reviewer]
        url = _run(*cmd)
    finally:
        _run("git", "checkout", original)
    print(url)
    return url


def process_session_data(session_data_file: str | Path, finalize: bool = False, root: str | Path = ".",
                         config: str | Path | None = None, now: datetime | None = None,
                         publish=publish_pull_request) -> dict:
    """Validate, re-check, write outputs, optionally open the PR, then save memory.
    Memory is saved only after publishing succeeds, so a failed push can be
    retried without the posts already being marked as seen."""
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    root = Path(root)
    rules = load_rules(config)
    state = State(root)                     # raises StateError if corrupt
    state.prune(now, rules.window_days)

    session = load_session(session_data_file)
    validate_counts(session)
    notes = recheck_against_state(session, state, rules.max_author_engagements,
                                  rules.window_days, now, rules.min_score)
    session.summary.engage_posts_count = len(session.engage_posts)

    output_file, skipped_file, body_file = get_session_paths(root, now)
    output_file.write_text(session.model_dump_json(indent=2, exclude={"skipped_posts"}), encoding="utf-8")
    if session.skipped_posts:
        skipped_file.write_text(json.dumps([p.model_dump() for p in session.skipped_posts], indent=2),
                                encoding="utf-8")
    body_file.write_text(render_pr_body(session, ts, notes), encoding="utf-8")

    if finalize and session.engage_posts:
        publish(str(output_file), str(skipped_file), str(body_file))

    # Record at proposal time, not after review: even a rejected reply means a
    # human looked at that post, and it shouldn't come back tomorrow.
    for p in session.engage_posts:
        state.record(p.link, p.author, ts)
    state.save()

    return {"output": str(output_file), "pr_body": str(body_file),
            "engage": len(session.engage_posts), "skipped": len(session.skipped_posts),
            "caught_at_output_pr": len(notes)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-data-file", required=True)
    ap.add_argument("--finalize", action="store_true", help="open a PR for review")
    args = ap.parse_args()
    try:
        result = process_session_data(args.session_data_file, finalize=args.finalize)
    except (SessionError, StateError, ConfigError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    if not args.finalize:
        print("Dry run. Re-run with --finalize to open the PR.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
