---
name: autoload-strategy
type: decision
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [memory]
---

# Autoload strategy

Two independent layers, so that the dynamic one can fail without losing the memory.

```mermaid
graph TD
    A["session start"] --> L1
    L1["<b>L1 static</b><br/>~/.claude/CLAUDE.md<br/>→ @~/.claude-memory/AUTOLOAD.md"]:::l1
    L1 --> L2{"SessionStart<br/>hook<br/>installed?"}
    L2 -->|yes| D["<b>L2 dynamic</b><br/>mem load → cwd scope,<br/>active project, STM, links"]:::l2
    L2 -->|no| F["identity and global<br/>policy only"]:::fb
    D --> C["session context"]:::out
    F --> C

    classDef l1 fill:#1f4d3a,stroke:#4dbd8a,color:#fff
    classDef l2 fill:#1f3a5f,stroke:#4a90d9,color:#fff
    classDef fb fill:#4d431f,stroke:#bda84d,color:#fff
    classDef out fill:#3f2b56,stroke:#9b6dd6,color:#fff
```

| Layer | Mechanism | Portability |
|---|---|---|
| L1 | static import in `~/.claude/CLAUDE.md` | identical on Linux/Windows/macOS, no executable |
| L2 | `SessionStart` hook → `mem load` | command written per-OS by the installer (`python3` vs `python`) |

**Why two layers:** the `~/.claude/` path exists the same way on every system, so L1 is portable unconditionally. The hook instead depends on the shell and on the Python binary's name, so it lives in `~/.claude/settings.json` — a machine-local file, not versioned in the repo. The repo stays OS-agnostic; only `install/setup.sh` and `install/setup.ps1` differ.

**No symlinks** towards `~/.claude/projects/*/memory`: on Windows they require elevated privileges. Explicit imports are used instead.

See also [[memory-architecture]] · [[global]]
