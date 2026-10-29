---
name: review-pr
description: Synchronize session analysis JSON with PR body decisions.
---
# Sync review decisions back from a PR

After review, the **PR body is the source of truth**. Given a PR number:

1. `gh pr view <N> --json headRefName,body` and `gh pr checkout <N>`.
2. For each post, read its **Decision**. If any still says `accept / reject`, **stop and ask the reviewer**. Don't guess.
3. `reject` → remove the post from `engage_posts` in the session JSON and append it to the session's `.skipped.json` with the reviewer's reason.
4. Reply edited in the PR → copy it exactly into `chosen_reply`. If the edit removed a product mention, set `brand_mention_analysis.mention_product = false` and record why.
5. Commit (`docs(session): sync review for <N>`), or an empty commit if nothing changed, then push.

Rejections and edits are the training signal: review them periodically and tighten `engage-criteria` or the config filters.
