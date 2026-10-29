"""Load workflow config from config/config.toml (copy config/config.template.toml).

Filter keywords and limits live in config, not code, so the same pipeline
works for any product without a code change."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CONFIG_ENV_VAR = "WORKFLOW_CONFIG_PATH"
DEFAULT_CONFIG_PATH = Path("config/config.toml")


class ConfigError(RuntimeError):
    """Raised when workflow configuration is missing or invalid."""


@dataclass(frozen=True)
class Rules:
    blocked_keywords: frozenset = field(default_factory=frozenset)
    max_reply_count: int = 300          # crowded thread: our reply gets buried
    max_post_age_hours: int = 48        # stale thread: nobody reads new replies
    max_author_engagements: int = 3     # per window
    window_days: int = 7                # also the TTL for seen-post memory
    min_score: int = 7                  # enforced in output_pr, not just asked for in the prompt

    def __post_init__(self):
        # Seen-memory must outlive the freshness window, or an old post could
        # age out of memory while still "fresh" and get proposed again.
        if self.window_days * 24 < self.max_post_age_hours:
            raise ConfigError("window_days must cover max_post_age_hours")


@dataclass(frozen=True)
class GithubConfig:
    repo_owner: str
    repo_name: str
    pr_reviewer: Optional[str] = None


def _resolve_config_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    env_path = os.environ.get(CONFIG_ENV_VAR)
    return Path(env_path).expanduser() if env_path else DEFAULT_CONFIG_PATH


def _load(path: str | Path | None = None) -> dict:
    p = _resolve_config_path(path)
    if not p.exists():
        raise ConfigError(f"{p} not found. Copy config/config.template.toml to config/config.toml.")
    with open(p, "rb") as f:
        return tomllib.load(f)


def load_rules(path: str | Path | None = None) -> Rules:
    filters = _load(path).get("filters", {})
    keywords = set()
    for group in filters.get("blocked_keywords", {}).values():
        keywords.update(k.lower() for k in group)
    limits = {k: v for k, v in filters.items() if k != "blocked_keywords"}
    return Rules(blocked_keywords=frozenset(keywords), **limits)


def load_github_config(path: str | Path | None = None) -> GithubConfig:
    gh = _load(path).get("github", {})
    try:
        return GithubConfig(repo_owner=gh["repo_owner"], repo_name=gh["repo_name"],
                            pr_reviewer=gh.get("pr_reviewer"))
    except KeyError as e:
        raise ConfigError(f"[github] is missing {e}") from e
