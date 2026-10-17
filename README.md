# orcaducho

A token-frugal multi-agent development harness for Claude Code, built on
[Orca](https://onorca.dev)'s orchestration layer.

```
You
└─ orcaducho:coordinator  (Opus · plans only, cannot edit code)
   ├─ orcaducho:worker    (Haiku → Sonnet on failure) · small task, own child worktree
   └─ orcaducho:lead      (Sonnet) · epic of more than 5 tasks, own child worktree + child Run
       └─ orcaducho:worker (Haiku → Sonnet)
```

## Why it is cheap

- **Opus only plans.** It never reads code, diffs, logs or issue threads, only 3-sentence `worker_done` summaries. Any codebase facts it needs come from a Haiku `Explore` subagent.
- **Haiku first.** Every task starts on Haiku. After a failed gate the worker gets one fix attempt; if it fails again the task is retried on Sonnet, and then escalated to the coordinator.
- **Deterministic before LLM.** Project checks run in a hook. An LLM review runs only for risky tasks:

  | risk | gate on `worker_done --outcome succeeded` |
  |---|---|
  | low  | clean tree + project `check` command |
  | med  | the above + headless Haiku diff review |
  | high | the above + headless Sonnet diff review |

- **Mechanics live in a script.** Worktree and terminal creation, merges, GitHub labels and comments are handled by `bin/orcaducho`, so no model tokens are spent on them.
- **Short agent prompts.** Each prompt is small, because every worker pays for it.

## Named agents in Orca

`worker-start --agent claude` only starts plain `claude`, so it cannot pick an agent definition. `orcaducho spawn` therefore:

1. creates the child worktree (`orca worktree create --parent-worktree …`) and sets its display name;
2. opens a terminal titled `orcaducho:<role> · <task>` that runs `claude --agent orcaducho:<role> --model <m> -n "orcaducho:<role> · <task>"`;
3. binds it under supervision with `orca orchestration worker-start --task <id> --terminal <handle>`.

The coordinator also names each Orca Task with `--task-title` and `--display-name`. The role is therefore visible on the terminal tab, the worktree, the Task, and the Claude session.

Orca treats a terminal bound with `--terminal` as *external*, so `worker-release` settles the worker but leaves the terminal open. `orcaducho release --dispatch <id>` runs `worker-release` first, then closes that terminal, and only once the worker has settled as succeeded or failed.

## State

- **GitHub issues:** one epic issue per objective, with one sub-issue per task (labels `orcaducho`, `risk:*`). Workers' summaries are mirrored as comments by a hook. The final PR `Closes #epic`.
- **Orca:** Run → Tasks (dependencies) → Dispatches. Orca decides what can run and when a task is settled.
- **`.orcaducho/plan.md`** in the run worktree, so the coordinator can resume after `/clear` without planning again.

## Install

```sh
/plugin marketplace add zugazagoitia/orcaducho
/plugin install orcaducho@orcaducho
python3 ~/.claude/plugins/marketplaces/orcaducho/bin/orcaducho install   # puts `orcaducho` on PATH (~/.local/bin)
```

Requirements: Orca ≥ 1.4, Claude Code ≥ 2.1, `python3`, `git`, and `gh` (optional, for issues).

## Use

From any Claude Code session in an Orca-managed repo:

```
/orcaducho:orcaducho add rate limiting to the login endpoint
```

Or from a shell inside Orca:

```sh
orcaducho start --name orcaducho/login-rate-limit "add rate limiting to the login endpoint"
```

## Per-project config: `.orcaducho.json`

The coordinator writes this file on first use if it is missing.

```json
{
  "check": "pnpm typecheck && pnpm lint && pnpm test",
  "base": "develop",
  "issues": true,
  "claudeArgs": ["--permission-mode", "acceptEdits"]
}
```

`claudeArgs` are passed to every orcaducho session. Workers run unattended, so a permission prompt stalls them. Either allow the Bash commands they need in your settings (`git`, `orca`, `orcaducho`, `gh`, and your check command), or use `["--dangerously-skip-permissions"]` if that is how you already run Claude in Orca.

## Development

`ORCADUCHO_PLUGIN_DIR=/path/to/checkout` makes every session orcaducho starts, and the reviewer, load the plugin from that checkout with `--plugin-dir` instead of the installed copy. Child sessions inherit the setting.

## Hooks

The hooks are inert unless `ORCADUCHO_ROLE` is set, so ordinary sessions are unaffected.

- `guard`: the coordinator may only write `.orcaducho/` and `.orcaducho.json`; workers may only write their `--owns` globs.
- `gate`: runs before `worker_done --outcome succeeded`, as described above. After two failures it tells the worker to report `failed`.
- `post`: mirrors `worker_done` onto the task's issue.

## License

MIT
