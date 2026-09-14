---
name: claude-memory
type: project
scope: project:claude-memory
fs_path: ~/.claude-memory
aliases: [claude-memory, mem.py]
repo: 
visibility: public
parent: 
status: active
lang: python
created: 2026-08-29
last_used: 2026-08-29
work_days: 1
last_work_day: 2026-09-14
---

# Persistent memory

## Purpose

Cross-session persistent memory for Claude Code on this machine: a Markdown wiki as the source of truth, a SQLite index, a garbage collector, and policy inheritance along the project tree.

## Status

Active. Upstream: to be configured after forking — `git remote add origin <url>`.

The repo contains the memory itself: commits that change it are work *on the memory*, not on a third-party project. Pushing stays manual — see [[push-policy]].

## Notes

- No external dependencies: Python stdlib only
- Must stay portable on Windows: no symlinks, `~`-relative paths

Decisions: [[memory-architecture]] · [[autoload-strategy]]

See also [[_graph]] · [[MEMORY]]
