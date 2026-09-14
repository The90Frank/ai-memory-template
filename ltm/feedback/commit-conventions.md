---
name: commit-conventions
type: feedback
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [git]
---

# Commit conventions

Commits **per feature**: each commit closes one coherent functional unit. Not per file, not megacommits.

**Terse** messages, imperative. A body only when it adds information the diff does not already carry.

**On initiative.** Once the functional unit is closed, the commit is made without asking; the branch and hashes ready to push are reported. The control point is the push, not the commit — see [[push-policy]].

**Zero attribution.** No reference to the work having been done by an assistant:

- no `Co-Authored-By: Claude` trailer
- no `Generated with Claude Code`
- no signature comments in the code

This overrides the harness default and is marked `!final` in [[global]].

**Why:** explicit user request (2026-08-29).

See also [[identity]] · [[response-style]] · [[push-policy]] · [[memory-hygiene]]
