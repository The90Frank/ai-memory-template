---
name: inheritance
type: policy
scope: global
created: 2026-08-29
pin: true
---

# Policy inheritance

Policies resolve by following the project's position on the filesystem: from the global root down to the most specific node.

```mermaid
graph TD
    G["policies/global.md"]:::root
    N["grandparent<br/><i>~/dev</i>"]
    P["parent<br/><i>~/dev/acme</i>"]
    S["project<br/><i>~/dev/acme/api</i>"]:::leaf
    E["effective policy"]:::out

    G --> N --> P --> S --> E

    classDef root fill:#1f3a5f,stroke:#4a90d9,color:#fff
    classDef leaf fill:#3f2b56,stroke:#9b6dd6,color:#fff
    classDef out fill:#1f4d3a,stroke:#4dbd8a,color:#fff
```

## Merge rules

| Type | Behaviour |
|---|---|
| scalar | override — the most specific one wins |
| list | append + dedup, order preserved |
| map | recursive merge, key by key |
| `!final` | the value locks: descendants cannot redefine it |
| `!local` | the value applies to this node only, it does not propagate to children |
| `~key` | removes the inherited key |

Conflict between two `!final` on the same branch: the ancestor wins, and the descendant is flagged by `mem doctor`.

## Resolution

1. Start from the `cwd` and walk up the directory chain
2. Every directory matching a registered project's `path` contributes its `policy.md`
3. `policies/global.md` is always the first link
4. Inspect the result with `mem scope <path>`

```bash
python3 bin/mem.py scope ~/dev/acme/api
```

## Example

`global` imposes `commit.attribution: none !final` and `commit.granularity: feature`.
The `acme/api` project may take granularity down to `atomic`, but it cannot reintroduce attribution.

See also [[global]] · [[MEMORY]]
