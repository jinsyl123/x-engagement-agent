---
name: engage-criteria
description: How to decide whether to reply, how to score a post, and how to draft the reply.
---
# Engagement criteria

Default to **skip**. A missed reply costs nothing; a bad one costs trust. Read `../product-info/SKILL.md` for what we genuinely know about.

## 1. Grounding first
Fill `grounding_analysis` before thinking about a reply: what is the post actually saying (`post_gist`), and what does the author want (`author_intent`: help, feedback, attention, to vent)?

## 2. Bridge test
Is there an honest, specific connection between this post and something we genuinely know? Fill `bridge_test_analysis`.
- `strong`: we can add a concrete fact, number, pitfall or technique the author doesn't have.
- `medium`: relevant, but add value without mentioning the product.
- `weak` / `none`: skip. Don't manufacture a connection.

## 3. Score (1–10), reasoning first
Write `analysis.reasoning`, *then* the score. Engage only at **7+** (also enforced in code).
The bar: *would a senior engineer reading this reply learn something concrete?*
Automatic skips: generic agreement ("great point!"), restating the post, anything that reads as an ad, research-paper link drops with no discussion.

## 4. Draft
- Brainstorm at least 2 `brainstormed_angles`, pick one as `chosen_reply`, keep the others as `alternatives`.
- ≤ 280 characters. Match the thread's tone. No hashtags, no emoji spam.
- Mention the product **only** if it directly answers the author's problem. Justify it in `brand_mention_analysis.reasoning` either way.
