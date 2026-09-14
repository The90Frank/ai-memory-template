---
name: sequential-execution
type: feedback
scope: global
created: 2026-08-29
last_used: 2026-08-29
uses: 1
confidence: high
pin: true
tags: [workflow]
---

# Sequential execution

Work proceeds **one step at a time**, always, in the declared order. At any moment the user must be able to say where things stand.

**Why:** explicit user request (2026-08-29). Concurrent work makes the state illegible from outside: if two things advance together, there is no longer a point where you are.

## The plan is approved first

**Every plan needs the user's explicit go-ahead before being executed.** Declaring the steps and starting in the same turn is not allowed: the plan is presented, and then you stop.

- the plan changed? present it again and wait again
- the go-ahead is for **that** plan: steps added afterwards need a new approval
- a correction to a single point is **not** a go-ahead for the whole plan
- nothing to approve only when there is no plan: a question, a read, a one-line answer

**Why:** a plan is for deciding together what to do, not for announcing what is already being done.

## How to apply it

- **declare the steps before starting**, then execute them in that order once cleared
- close one before opening the next, reporting the outcome
- if a step changes the plan, say so and re-declare the remaining steps
- when work is interrupted or suspended: say which step was the last completed and what the next would be

## Forbidden without an explicit request

| What | Why it breaks the rule |
|---|---|
| parallel subagents | several workflows, no single state |
| background tasks | they advance while the conversation is elsewhere |
| jumping ahead to a later step | the declared order stops describing reality |
| merging several steps into one shot | the intermediate outcome is no longer observable |

## Limit

The rule concerns **work steps**, not the atomic reads that sit inside a step: reading three files to answer one question is a single step, and grouping those reads hides nothing. What is never merged are the **state-changing actions** — edits, commands, commits: those go one at a time, with the outcome reported.

See also [[response-style]] · [[commit-conventions]] · [[push-policy]] · [[global]]
