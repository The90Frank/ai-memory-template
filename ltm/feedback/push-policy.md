---
name: push-policy
type: feedback
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [git, workflow]
---

# Division of labour on git

**Claude commits, the user pushes.** Base rule, valid on every repo unless the individual request explicitly says otherwise.

**Why:** the user wants a control point before anything becomes public. A commit is local and reversible; a push is not.

**How to apply it:**

- take the work up to the commit and stop there
- leave the working tree clean and say which branch holds the commits that are ready
- no `git push`, no `--force`, no creating PRs or releases on your own initiative
- configuring remotes and branches is allowed: it prepares the ground, it does not publish
- an explicit "push it" in the current request counts for that time only

See also [[commit-conventions]] · [[response-style]] · [[global]]
