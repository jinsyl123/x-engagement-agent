# Run an engagement session

You are the orchestrator. Steps run in order; don't skip or reorder.

1. **Fetch.** Follow `fetch-and-triage.md` to collect candidate posts with the browser tool.
2. **Filter.** For *every* candidate, pipe it through the rule filter and obey the result:
   ```bash
   echo '{"link": "...", "author": "@...", "content": "...", "reply_count": 12, "timestamp": "..."}' \
     | python -m agent.skip_filter config.toml
   ```
   `skip` → add to `skipped_posts` with the given reason. `keep` → continue to step 3.
3. **Judge and draft.** For each kept post, follow `reply-criteria.md`. Skipping is a valid outcome and usually the right one.
4. **Write `session-output.json`** matching `agent/schemas.py` exactly. `summary.posts_analyzed` must equal engaged + skipped.
5. **Finalize.**
   ```bash
   python -m agent.finalize session-output.json --publish
   ```
   If it fails, read the error, fix `session-output.json`, and re-run. Never edit files under `state/` by hand.
