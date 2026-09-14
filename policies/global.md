---
name: global
type: policy
scope: global
created: 2026-08-29
pin: true
---

# Global policy

Root of the inheritance chain. Every project inherits from here and may redefine anything not marked `!final`. Mechanics in [[inheritance]].

> 📌 **Fork checklist** — the values below are one worked example, not a recommendation.
> Rewrite them to match how *you* work, then delete this quote block. The keys are free
> form: `mem` merges whatever you declare, it does not validate a fixed schema.

```yaml policy
lang:
  chat: en
  code: en
  commit: en
  pr: en
  docs_official: en
  docs_internal: en
  docs_ambiguous: ask
  memory_repo_commit: en

response:
  style: concise-schematic   !final
  prose: avoid
  format: [bullet, tables, trees, mermaid]

workflow:
  execution: sequential      !final
  plan_approval: required    !final
  progress: announce-steps
  background_tasks: none
  subagents: on-request-only

git:
  identity_by: host
  identity:
    github:
      user_name: <YOUR-HANDLE>
      user_email: <you@example.com>
  default_branch: main
  machine_branch: required   !final
  main_frozen: true          !final
  push: manual-user-only     !final
  commit:
    granularity: feature
    trigger: on-feature-complete
    attribution: none        !final
    style: imperative-short
    body: only-if-informative

paths:
  scratch: ~/Documents/claude-workspace
  scratch_retention: disposable   !final

docs:
  format: markdown           !final
  diagrams: mermaid          !final
  style: wiki-linked

memory:
  stm_work_ttl: 10
  stm_cap_days: 180
  stm_ttl_days: 14
  stm_write: proactive-session-end
  promote_after: 2
  evict_after_days: 180
  autoload_budget_kb: 8
  load_budget_kb: 10
  project_registration: ask-first
  repo_visibility: public
  tags: [architecture, git, identity, memory, workflow]

secrets:
  never_store: true          !final
  pointers_only: true

portability:
  targets: [linux, windows, macos]
  no_symlinks: true          !final
  python: stdlib-only
  paths: home-relative
```

## Notes

- `lang` — **whatever ends up in a repo is in English**: code, identifiers, comments, commit messages, PR bodies. Documentation splits by **audience**, not by preferred language: *official* (leaves the team) and *internal* (stays in the team) may differ. ⚠️ **When it is unclear which of the two, ask** — guessing has already cost a rewrite. If you chat in another language, set `chat` to it and leave the rest in English: the split between "what I say" and "what gets committed" is the point of this key.
- `git.identity_by: host` — **the identity is chosen by the repo's host**, not by work-vs-personal and not by the machine. On **GitHub the identity is always the same**, including for work repos inside an organization: you enter an org with your own account. ⚠️ **Other hosts are not here**: the identity for a corporate GitLab or a client's server is discovered and recorded **on the branch of the machine that uses it**, never assumed to be the personal one. Even *where* to configure it — global or repo-local — depends on what already occupies the global config on that machine. Details in [[git-identity]].
- `attribution: none` — no signature, no `Co-Authored-By` trailer and no comment crediting the work to an assistant, neither in commits nor in code.
- `machine_branch` · `main_frozen` — every machine commits on its own branch, born from `main`; branches are permanent forks that never come back. `main` takes no further commits. The machine's identity is read from `git branch --show-current`. Details in [[machine-branches]].
- `push: manual-user-only` — Claude stops at the commit; the push belongs to the user. Configuring remotes and branches is allowed. Details in [[push-policy]].
- `never_store` — credentials, tokens and keys never enter memory: only where to find them is saved (secret manager name, file path, environment variable).
- `autoload_budget_kb` — cap on what the static layer injects into every session; past the threshold the GC compacts.
- `load_budget_kb` — cap on the `mem load` output, that is **layer 2**. ⚠️ The hook injecting it **truncates silently** past that limit, and what falls off is the tail: the LTM facts. So `load` clips the project body itself, stating where the rest is, and `mem doctor` measures the output **for every registered project** — the size depends on the cwd, and from inside a large project it is three times what it is from a generic directory.
- `workflow.execution: sequential` — one step at a time, in the declared order, with the outcome reported before moving to the next. No subagents or background tasks unless asked. Details in [[sequential-execution]].
- `plan_approval: required` — the plan is presented and an explicit go-ahead is awaited. Presenting it and starting in the same turn is not allowed; a correction to one point is not an approval.
- `scratch_retention: disposable` — whatever sits in `~/Documents/claude-workspace` must be deletable without consequence. What becomes important is moved out before closing. Details in [[workspace-scratch]].
- `stm_work_ttl` — **STM expiry is measured in work days on the project, not calendar days.** Every day in which at least one session is opened on a project increments its `work_days` counter; a note is born tagged with the current tick and expires once `stm_work_ttl` more have passed. Two weeks without opening a project contain no information that invalidates its notes, and must not consume their life. Details and traps in [[stm-work-counter]].
- `stm_cap_days` — a calendar cap that applies **regardless**, even with the counter frozen: it stops a note from becoming immortal because the project has been dormant for a year while the code changed at someone else's hands. Whichever of the two arrives first wins. On a rarely opened project it must be loosened, otherwise it kills notes **before** the counter does and the calendar is back in charge through the back door.
- `stm_ttl_days` — fallback regime for notes without `created_work_day`: without it, a note born before the counter would never expire. It is no longer the main mechanism.
- `promote_after` — confirmations needed before promoting an STM note to LTM. They are recorded with `mem confirm <note>`: a confirmation is a **declared act**, not something inferred from `load` injecting the note. `mem doctor` flags it once the threshold is reached; promotion stays manual because choosing the type is a semantic call.
- `commit.trigger` · `stm_write` · `project_registration` — where initiative sits and where a go-ahead is needed. Details in [[memory-hygiene]].
- `repo_visibility: public` — the upstream is public, so internal paths, client names and proprietary architectures are **not** recorded: they would go online on the first push. `never_store` applies regardless. Anyone forking onto a private upstream sets this to `private` and rereads [[memory-hygiene]] first.

- `memory.tags` — **closed vocabulary**: a tag outside this list is a problem for `mem doctor`, which suggests the nearest one that already exists. It exists to stop the vocabulary from growing back. A tag exists to create a grouping **that text search cannot do**: if the word is already in the title or body, `mem search` finds the note without it, and a tag used once is a label rather than an index. Adding a tag means editing this list, deliberately.

See also [[MEMORY]] · [[_graph]]
