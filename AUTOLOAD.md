---
name: AUTOLOAD
type: reference
scope: global
created: 2026-08-29
pin: true
---

# Permanent context

This file is loaded into every Claude Code session on this machine. Keep it under 8 KB.

> 📌 **Fork checklist** — this file is an example. Rewrite the sections below with your own
> identity, your own invariants and your own paths, then delete this quote block.

## Identity

- On **GitHub**: `<YOUR-HANDLE>` — `<you@example.com>`. Applies everywhere, **including work repos inside an organization**
- ⚠️ **The git identity is chosen by the host**: other hosts have their own identities, discovered and recorded on the machine's branch. See [[git-identity]]
- Language: **chat in English** · code, comments, commits and PRs **in English**. *Official* docs en, *internal* docs en — when it is unclear which, **ask**. See [[global]]

## Invariant rules

Not redefinable by any project (`!final` in [[global]]):

1. **Concise, schematic answers** — bullets, tables, diagrams. No long prose, no preambles.
2. **Plan first, then a go-ahead** — state the steps and **stop** until the user approves. Presenting a plan and starting to execute it in the same turn is not allowed; if the plan changes, it is presented again.
3. **Sequential execution** — one step at a time, in the declared order, outcome reported before the next step. No parallel subagents, no background tasks without a request. The user must always know where things stand.
4. **One commit per feature**, imperative and short message. A body only when it adds information.
5. **Zero attribution** — no signature, no `Co-Authored-By` trailer, no comment crediting the work to an assistant, neither in commits nor in code.
6. **The user does the pushing** — stop at the commit. Configuring a remote yes, publishing no, unless explicitly asked in the moment.
7. **One branch per machine** — commit on the current machine's branch (`git branch --show-current`), never on `main`, which is frozen. Branches are permanent forks: they are not merged. Another machine's memory is read with `git show origin/<branch>:<file>`.
8. **Documentation in Markdown, diagrams in Mermaid.** Always.
9. **Secrets never in memory** — record only where to find them.
10. **`~/Documents/claude-workspace` is disposable** — throwaway scripts, caches, prototypes. Deleting it at the end of a job must matter to nobody: whatever becomes important is moved out first.
11. **Portability** — Linux, Windows, macOS: no symlinks, `~`-relative paths, Python stdlib.

## Memory

Repo: `~/.claude-memory` (git). CLI: `python3 ~/.claude-memory/bin/mem.py`.

- **STM** `stm/<project>/` — working notes, low confidence, not authoritative
- **LTM** `ltm/<type>/` — one fact per file, stable, citable
- **STM notes expire in _work_ days on the project, not calendar days**: two weeks without opening a project do not consume their life. A calendar cap applies anyway, 180d. See [[stm-work-counter]]
- An STM fact reconfirmed twice, or marked `pin`, should be promoted to LTM. **A confirmation is a declared act**: record it with `mem confirm <note>`, and `mem doctor` flags it once the threshold is reached
- The garbage collector archives, it does not delete, and **must be run by hand**: the only automations are `mem load` at session start and `mem project` on every prompt

### Finding things

⚠️ **The context you get at startup is a fraction of the memory**: `load` injects the most recent LTM facts and nothing else. `reference` notes are never seen unless you search for them.

```bash
python3 ~/.claude-memory/bin/mem.py search <term>      # tag, name, title, body
python3 ~/.claude-memory/bin/mem.py tags [filter]      # closed vocabulary
```

The body is searched by default: tags alone do not hold. Filters: `--tag` (AND), `--type`, `--scope`, `--meta`.

### Which project is active

Two independent sources: the **cwd** (`mem load`, at startup) and the **prompt** (`mem project`, `UserPromptSubmit` hook). The second matters when a session starts outside the project directory — without it the project layer never activates, `work_days` never advances, and STM notes stop expiring on work.

🔒 **Read-only task?** `--no-tick` on `project` and `load`: they read without writing either the counter or the session state. Use it when you need the project context but must leave no trace.

Inference matches the `aliases` declared in `projects/<slug>/project.md`, on word boundaries, and injects only on a change. Two projects named together: it says so and injects nothing. ⚠️ A match on a single alias may be a false positive — the header always states what it was inferred from. To force it: `mem project <slug>`.

When a durable fact emerges about the user, a project or a technical decision, write it to memory before closing the job.

**Initiative** — by default: an STM note at the end of a job yes, a commit on a closed feature yes, `mem new project` for a new directory **no, ask first**. Private upstream: paths and architectures may be recorded, secrets never. See [[memory-hygiene]].

## Per-project policy

Policies are inherited along the directory tree: global → grandparent → parent → project. To see the effective ones in the current context:

```bash
python3 ~/.claude-memory/bin/mem.py scope .
```

Full index: [[MEMORY]] · Projects: [[_graph]] · Mechanics: [[inheritance]]
