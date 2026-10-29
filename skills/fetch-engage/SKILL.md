---
name: fetch-engage
description: Scan the X home feed and collect candidate posts with the browser tool.
---
# Fetch candidates

Open https://x.com in the browser tool and scroll the home feed. Collect up to **5 candidates** that pass `check_skip` (a cap, not a quota: if the feed runs dry, stop with fewer).

For each post, record: `link` (canonical status URL), `author` (handle), `content` (full text, expanded), `reply_count`, `timestamp` (ISO 8601, UTC).

Browser rules:
- Expand truncated posts before recording `content`. A judgment on half a post is a wrong judgment.
- If the feed looks stagnant (no new posts after scrolling), refresh once, wait, and continue. If it's still stagnant, stop.
- If an element doesn't respond after 3 tries, record the post as skipped with reason `"browser: could not load"` and move on. Don't loop.
- Don't like, follow or reply. This step only reads. Don't make up posts.
