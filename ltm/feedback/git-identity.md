---
name: git-identity
type: feedback
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [git, identity]
---

# Which git identity to use

🔑 **The discriminator is the repo's host**, not work-vs-personal and not the machine.

## GitHub — applies on every machine

| | |
|---|---|
| `user.name` | `<YOUR-HANDLE>` |
| `user.email` | `<you@example.com>` |

⚠️ **This applies to work repos too.** A client's organizations are reached with your own personal account: **you do not enter an org under a second identity.**

## Other hosts do not live here

A corporate GitLab, a client's git server: the identity is **different**, and it is **discovered, not assumed**. It gets recorded on the branch of the machine that uses it — see [[machine-branches]].

The same goes for **where** the GitHub identity is configured: if `git config --global` on that machine is already taken by another host, GitHub must be set **repo-locally**; if it is not, the global config is fine. That is a fact about the machine, not about the rule.

## How to apply it

- 🔑 **Before committing, check which identity is active in the repo.** This is the easy mistake: the one used most on a machine ends up where it should not.
- On a new GitHub repo: set the identity **right after cloning**, if the global one is not already correct.
- On a repo hosted elsewhere: **touch nothing** if it is already configured — it is almost always the right one.

**Why:** the user had to get the messages of a private branch rewritten after the wrong email had been applied to it, together with a formal style and a sign-off.

## ⚠️ Trap: commits from GitHub's web editor

A commit made from the **web interface** does not use the real email but a noreply `<id>+<user>@users.noreply.github.com`. Several projects have identity checks that **reject** it:

> *"author email … must be a real email and cannot end in @users.noreply.github.com"*

⇒ If the target repo has that check, **the web editor is not enough**: commit locally with the real email, or rewrite the commit with `git commit-tree`, setting `GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_EMAIL`.

See also [[identity]] · [[commit-conventions]] · [[push-policy]] · [[global]]
