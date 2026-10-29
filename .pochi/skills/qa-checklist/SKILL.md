---
name: qa-checklist
description: Manual checks for the reviewer before approving a session PR.
---
# Reviewer QA checklist

For each proposed reply:
- [ ] Does the reply answer what the author actually asked (check `grounding_analysis`)?
- [ ] Is every factual claim true and something we'd stand behind publicly?
- [ ] Would a senior engineer learn something concrete from it?
- [ ] If the product is mentioned: does it directly solve the author's problem?
- [ ] ≤ 280 characters, matches the thread's tone, no hashtags.
- [ ] Not a second reply to the same person this week.

Then set each **Decision** to `accept` or `reject: <reason>`.
