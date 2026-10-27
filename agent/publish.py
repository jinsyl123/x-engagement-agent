"""Open one PR per session. The PR is the review UI: reviewers already live
in GitHub, comments and edits are tracked, and merge history is an audit
trail of every reply that went out and who approved it."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def open_pr(output_file: str, body_file: str, base: str = "main") -> str:
    if _run("git", "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Working tree has uncommitted changes; refusing to branch.")
    stem = Path(output_file).parent.name + "-" + Path(output_file).stem
    branch = f"session/{stem}"
    original = _run("git", "rev-parse", "--abbrev-ref", "HEAD")
    try:
        _run("git", "checkout", "-b", branch, base)
        _run("git", "add", output_file, body_file, "state")
        _run("git", "commit", "-m", f"session: {stem}")
        _run("git", "push", "-u", "origin", branch)
        url = _run("gh", "pr", "create", "--base", base, "--head", branch,
                   "--title", f"Engagement session {stem}", "--body-file", body_file)
    finally:
        _run("git", "checkout", original)
    print(url)
    return url
