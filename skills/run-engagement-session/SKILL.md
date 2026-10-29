---
name: run-engagement-session
description: Orchestrate the X engagement workflow (Fetch -> Filter -> Judge -> Finalize).
---
# X Engagement Workflow

Run with the `run.sh` launcher, which creates `.venv` and installs dependencies on first run. Steps run in order; don't skip or reorder.

1. **Fetch.** Follow `../fetch-engage/SKILL.md` to collect candidate posts with the browser tool.
2. **Filter.** For *every* candidate, pipe it through the rule filter and obey the result:
   ```bash
   echo '{"link": "...", "author": "@...", "content": "...", "reply_count": 12, "timestamp": "..."}' \
     | ./run.sh -m scripts.check_skip
   ```
   `skip` → add to `skipped_posts` with the given reason. `keep` → continue to step 3.
3. **Judge and draft.** For each kept post, follow `../engage-criteria/SKILL.md`. Skipping is a valid outcome and usually the right one.
4. **Write `session-output.json`** matching the models in `scripts/output_pr.py` exactly. `summary.posts_analyzed` must equal engaged + skipped.
5. **Finalize.**
   ```bash
   ./run.sh -m scripts.output_pr --session-data-file session-output.json --finalize
   ```
   If it fails, read the error, fix `session-output.json`, and re-run. Never edit `seen_posts.json` or `engagement_cache.json` by hand.
6. After a teammate reviews the PR, follow `../review-pr/SKILL.md`.
