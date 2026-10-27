# Fetch and triage

Collect up to 30 recent posts from the configured searches and lists.

For each post, record: `link` (canonical status URL), `author` (handle), `content` (full text, expanded), `reply_count`, `timestamp` (ISO 8601, UTC).

Browser rules:
- Expand truncated posts before recording `content`. A judgment on half a post is a wrong judgment.
- If an element doesn't respond after 3 tries, record the post as skipped with reason `"browser: could not load"` and move on. Don't loop.
- Don't like, follow or reply. This step only reads.
