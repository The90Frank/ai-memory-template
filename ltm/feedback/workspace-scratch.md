---
name: workspace-scratch
type: feedback
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [workflow]
---

# The workspace is disposable

`~/Documents/claude-workspace` is **staging space**: self-contained utility scripts, caches, experiments against the real environment. There is a single criterion:

> at the end of a job, deleting the whole directory must matter to nobody.

**Why:** explicit user request (2026-08-29). There has to be a place to create freely without the ambiguity "can this be thrown away?" ever arising.

## What belongs here

- scripts that check whether a conversion works against the real environment
- intermediate output, dumps, working caches
- prototypes thrown away as soon as they have answered the question

## What does not

| What | Where it goes instead |
|---|---|
| code someone will reuse | in the project's repo |
| facts and decisions | `~/.claude-memory` |
| the only copy of something | in a versioned repo |

If something born here becomes important, it **must be moved before closing the job** — and that fact has to be said, not assumed.

## Corollaries

- the directory is **not registered as a project**: it is not work, it is a test bench (see [[memory-hygiene]])
- no `git init` in here: versioning implies it is worth keeping
- distinct from the session scratchpad (`/tmp/claude-*`), which dies with the session: the workspace survives across sessions, but is not authoritative either
- at the end of a job it helps to say what is left in there, so it is clear it can be deleted

See also [[sequential-execution]] · [[memory-hygiene]] · [[global]]
