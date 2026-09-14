---
name: memory-hygiene
type: feedback
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [memory]
---

# Initiative and scope when writing memory

Decided on 2026-08-29. Governs the three things the policies did not cover: when to write on my own initiative, when to ask, and what may be written at all.

| Action | Default |
|---|---|
| STM note at the end of a session | **on initiative** |
| Durable fact into LTM | on initiative |
| Registering a new project | **ask first** |
| Promoting STM → LTM | on initiative, at the second confirmation — recorded with `mem confirm` |

## STM at the end of a session

Before closing a non-trivial job, write into `stm/<project>/` whatever is not derivable from the code or the diff: the state reached, hypotheses not yet verified, what to pick up next. It expires after `stm_work_ttl` **work** days on the project, not calendar days: see [[stm-work-counter]].

**Why:** without proactive writing the `promote_after: 2` cycle never has anything to promote, and the STM architecture stays inert — which was the case until today (0 notes).

It is not a session log: if a note is of no use to whoever resumes the work, it should not be written.

## Project registration

A directory with no registered project: **flag it and wait for the go-ahead**, do not run `mem new project` on your own initiative. In the meantime, work with the global policies alone.

**Why:** it keeps the project tree from filling up with nodes for throwaway jobs.

## Scope

🔑 **What may be recorded depends on `repo_visibility` in [[global]], and on nothing else.**

| `repo_visibility` | What may be recorded |
|---|---|
| `private` | project names, internal paths, architectures and work decisions |
| `public` | only what could be published as-is — no client names, no internal paths, no proprietary architectures |

This fork ships with `public`. If your upstream is private, set it to `private` and this section loosens accordingly.

`secrets.never_store` (`!final`) is unaffected either way: credentials, tokens and keys never enter memory, not even in a private repo — only where to find them is recorded. If the repo's visibility changes, this fact is the first one to revisit.

See also [[push-policy]] · [[commit-conventions]] · [[memory-architecture]] · [[global]]
