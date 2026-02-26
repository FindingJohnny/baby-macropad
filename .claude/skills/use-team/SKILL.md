---
name: use-team
description: Reference card for spawning agent teammates using Teams (not plain subagents). Invoke with /use-team when you catch yourself about to use run_in_background.
---

# Use Agent Teams (NOT Subagents)

**Rule**: NEVER use `Task` with `run_in_background: true`. That creates invisible subagents. ALWAYS use Teams.

## Correct Pattern

### 1. Create a team
```
TeamCreate(team_name="sprint-7")
```

### 2. Spawn teammates into the team
```
Task(
  team_name="sprint-7",
  name="backend-auth",
  subagent_type="backend-dev",
  prompt="Implement the auth middleware per spec..."
)
```
- `team_name` — the team you created
- `name` — unique name for this teammate (shows in UI)
- `subagent_type` — agent definition from `.claude/agents/` (see below)
- `prompt` — the work assignment

### 3. Coordinate
```
SendMessage(team_name="sprint-7", name="backend-auth", message="Rebase on develop before PR")
```

## Available Agent Types

| `subagent_type` | Role |
|---|---|
| `backend-dev` | Fastify + Prisma API work |
| `ios-dev` | SwiftUI iOS app work |
| `infra-dev` | Docker, CI/CD, deploy scripts |
| `code-reviewer` | PR review (watch for false positives) |
| `debugger` | Investigate failures, read logs |
| `docs-auditor` | Spec/docs consistency checks |
| `coordinator` | Orchestrate multi-agent sprints |
| `qe` | Write and run tests |
| `qa-ux` | UX review, snapshot validation |

Agent definitions live in `.claude/agents/*.md` in the main baby-basics repo.

## What NOT to Do

```
# WRONG — creates invisible subagent, not a teammate
Task(run_in_background=true, prompt="do the thing")
```

```
# WRONG — no team_name, so it's a detached subagent
Task(prompt="do the thing")
```

## Quick Checklist

- [ ] `TeamCreate` called first?
- [ ] `Task` has both `team_name` and `name`?
- [ ] `subagent_type` matches an agent file?
- [ ] `run_in_background` is NOT set?
