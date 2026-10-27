# Sync review decisions back from a PR

The PR body is the **source of truth** after review. Given a PR number:

1. `gh pr view <N> --json headRefName,body` and `gh pr checkout <N>`.
2. For each post, read its **Decision**. If any still says `accept / reject`, **stop and ask the reviewer**. Don't guess.
3. `reject` → remove the post from `engage_posts` in the session JSON, append it to `skipped_posts` with the reviewer's reason.
4. Reply text edited in the PR → copy it exactly into `chosen_reply`. If the edit removed a product mention, set `brand_mention.mentions_product = false` and record why.
5. Commit (`session: sync review for <N>`), or an empty commit if nothing changed, then push.

Rejections and edits are the training signal: review them periodically and tighten `reply-criteria.md` or the config filters.
