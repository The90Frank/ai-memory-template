---
name: memory-architecture
type: decision
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [memory, architecture]
---

# Memory architecture

Decision of 2026-08-29. Repo `~/.claude-memory`, upstream managed by the user.

**Choice: Markdown wiki + SQLite index.**

```mermaid
graph LR
    MD["Markdown<br/><b>source of truth</b><br/>versioned in git"]:::src
    DB[("SQLite<br/>index<br/><i>git-ignored</i>")]:::idx
    OUT["generated Mermaid<br/>GC · query · scope"]:::out

    MD -->|"mem index"| DB
    DB -->|"mem graph / gc / load"| OUT
    OUT -->|"rewrites"| MD

    classDef src fill:#1f4d3a,stroke:#4dbd8a,color:#fff
    classDef idx fill:#1f3a5f,stroke:#4a90d9,color:#fff
    classDef out fill:#3f2b56,stroke:#9b6dd6,color:#fff
```

## Rejected alternatives

| Option | Reason for rejection |
|---|---|
| Flat files only, manual GC | no querying over the links, whole index in context every session |
| Hook resolver without a Markdown wiki | the user wants all documentation as a Markdown + Mermaid wiki |
| DB as the source of truth | git diffs become unreadable and the memory is no longer inspectable by hand |

## Fixed constraints

- the DB never holds original information: `mem index` rebuilds it from scratch
- the GC **archives**, it does not delete — and history stays in git regardless
- Python stdlib only, no symlinks, `~`-relative paths: the repo must behave identically on Windows

⚠️ The calendar TTL described here was superseded on 2026-08-30: STM notes expire in
**work days on the project**. See [[stm-work-counter]].

See also [[global]] · [[inheritance]] · [[autoload-strategy]] · [[stm-work-counter]]
