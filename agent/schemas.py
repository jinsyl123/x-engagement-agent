"""The contract between the LLM and the rest of the system.

The agent writes a session file; nothing downstream trusts it until it parses
against these models. The fields also force the reasoning order I wanted the
model to follow: understand the post (grounding) → decide whether there's a
genuine bridge to our domain → brainstorm angles → pick a reply → justify any
brand mention. Requiring each step as a field makes skipped thinking visible
in review instead of hidden in a fluent reply.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Grounding(BaseModel):
    post_gist: str = Field(min_length=1)
    author_intent: str               # asking for help? sharing a win? venting?
    core_concepts: List[str]


class BridgeTest(BaseModel):
    """Is there an honest connection between this post and what we know?
    If not, decision=False and we shouldn't be in the thread."""
    connection_point: str
    strength: str                    # "strong" | "weak" | "none"
    decision: bool


class Angle(BaseModel):
    strategy: str                    # e.g. "add a data point", "share a pitfall"
    summary: str


class Reasoning(BaseModel):
    assessed_topic: str
    social_intent: str
    bridge_test: BridgeTest
    angles: List[Angle] = Field(min_length=1)


class Alternative(BaseModel):
    reply: str
    strategy: str


class BrandMention(BaseModel):
    mentions_product: bool
    reasoning: str                   # why a mention helps the reader, or why we left it out


class Reply(BaseModel):
    reasoning: Reasoning
    chosen_reply: str = Field(min_length=1, max_length=280)
    why_this_reply: str
    alternatives: List[Alternative]
    brand_mention: BrandMention


class Score(BaseModel):
    score: int = Field(ge=1, le=10)
    reasoning: str


class EngagePost(BaseModel):
    link: str
    author: str
    excerpt: str
    prior_engagements: int = Field(ge=0)
    score: Score
    grounding: Grounding
    reply: Reply


class SkippedPost(BaseModel):
    link: str
    author: str = ""
    reason: str


class Summary(BaseModel):
    posts_analyzed: int = Field(ge=0)


class Session(BaseModel):
    summary: Summary
    engage_posts: List[EngagePost] = []
    skipped_posts: List[SkippedPost] = []
    notes: Optional[str] = None
