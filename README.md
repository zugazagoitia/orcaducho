# orcaducho

A token-frugal multi-agent development harness for [Claude Code](https://claude.com/claude-code), built on [Orca](https://onorca.dev)'s orchestration layer.

You give it an objective. An Opus coordinator plans it into GitHub issues and Orca Tasks, then dispatches cheap named workers, each in its own worktree. It merges their work and opens **one PR** for you to review.

```
You
└─ orcaducho:coordinator  (Opus · plans only, cannot edit code)
   ├─ orcaducho:worker    (Haiku → Sonnet on failure) · small task, own child worktree
   └─ orcaducho:lead      (Sonnet) · epic of more than 5 tasks, own child worktree + child Run
       └─ orcaducho:worker (Haiku → Sonnet)
```

## Quick start

```sh
curl -fsSL https://raw.githubusercontent.com/zugazagoitia/orcaducho/main/install.sh | sh   # once per machine
orcaducho init --check "pnpm typecheck && pnpm test"                                        # once per repo
```

Then, in Claude Code inside an Orca terminal: `/orcaducho:orcaducho <objective>`.

## Contents

- [Requirements](#requirements)
- [Install](#install)
- [Set up a project](#set-up-a-project)
- [Usage](#usage)
- [How it works](#how-it-works)
- [Command reference](#command-reference)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Update and uninstall](#update-and-uninstall)
- [Development](#development)

## Requirements

| Tool | Version | Used for |
|---|---|---|
| [Orca](https://onorca.dev) | ≥ 1.4 | worktrees, terminals, Runs/Tasks/Dispatches |
| Claude Code | ≥ 2.1 | the agents (`claude --agent`, plugins) |
| Python | ≥ 3.9 | the `orcaducho` CLI and hooks (stdlib only) |
| git | any recent | branches and merges |
| [GitHub CLI](https://cli.github.com) `gh` | optional | issues and the final PR (`gh auth login` first) |

The repository must be added to Orca, and you run orcaducho from a terminal **inside Orca**.

**Platforms and shells:** macOS and Linux, with a login shell of sh, bash, zsh or fish.
- Nothing in orcaducho depends on your shell. Agents are started through a generated POSIX `sh` launcher, so Orca's terminal only ever runs `sh "<path>"`.
- `install.sh` is plain POSIX sh, so it works under dash too.
- The CLI uses only the Python standard library (3.9+).
- Your `check` command always runs with `/bin/sh`.

## Install

**One line:**

```sh
curl -fsSL https://raw.githubusercontent.com/zugazagoitia/orcaducho/main/install.sh | sh
```

[`install.sh`](install.sh) checks the requirements, adds the marketplace, installs the plugin and puts the `orcaducho` CLI in `~/.local/bin` (override with `ORCADUCHO_BIN_DIR`). It is safe to run again; append `-s -- --update` after `sh` to also pull the latest version.

**Manually:**

1. In Claude Code, add the marketplace and install the plugin:

   ```
   /plugin marketplace add zugazagoitia/orcaducho
   /plugin install orcaducho@orcaducho
   ```

2. In a shell, put the `orcaducho` CLI on your PATH. This symlinks it into `~/.local/bin`, or into the directory you pass with `--dir`:

   ```sh
   python3 ~/.claude/plugins/marketplaces/orcaducho/bin/orcaducho install
   ```

   Make sure `~/.local/bin` is on your `PATH`:
   - fish: `fish_add_path ~/.local/bin`
   - zsh: add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc`
   - bash: add the same line to `~/.bashrc` on Linux, or `~/.bash_profile` on macOS

3. Restart Claude Code, then check that everything is visible:
   - `orcaducho --help` works in a shell.
   - `/agents` in Claude Code lists `orcaducho:coordinator`, `:lead`, `:worker` and `:reviewer`.

## Set up a project

In each repository, run:

```sh
orcaducho init --check "pnpm typecheck && pnpm lint && pnpm test" [--base develop] [--skip-permissions] [--no-issues]
```

This writes `.orcaducho.json` and adds `.orcaducho/` to the repo's local git exclude list. `--base` defaults to origin's default branch. You can also write the file by hand; if it is missing, the coordinator writes a first version on its own.

```json
{
  "check": "pnpm typecheck && pnpm lint && pnpm test",
  "base": "develop",
  "issues": true,
  "claudeArgs": ["--permission-mode", "acceptEdits"]
}
```

- **`check`:** your fast verification command. It runs before any worker can report success.
- **`base`:** the branch the run starts from and the final PR targets.
- **Permissions:** workers run unattended, so a permission prompt stalls them. Pick one:
  - Allow what they need in `.claude/settings.json`, e.g. `"permissions": {"allow": ["Bash(git *)", "Bash(orca *)", "Bash(orcaducho *)", "Bash(gh *)", "Bash(pnpm *)"]}`.
  - Set `"claudeArgs": ["--dangerously-skip-permissions"]`, only if that is already how you run Claude in Orca.
- **Issues:** with `gh` logged in and Issues enabled on the repo, orcaducho creates the labels `orcaducho`, `risk:low|med|high` and `status:failed` automatically. Set `"issues": false` to skip GitHub entirely.

`.orcaducho/` holds the coordinator's resumable plan. `orcaducho init` already keeps it out of git; if you skipped `init`, add it to `.gitignore`.

## Usage

### Start a run

From any Claude Code session running in an Orca terminal:

```
/orcaducho:orcaducho add rate limiting to the login endpoint
```

Or from a shell inside Orca:

```sh
orcaducho start --name orcaducho/login-rate-limit "add rate limiting to the login endpoint"
```

`--name` creates a new worktree and branch for the run and opens the coordinator there. Without `--name`, the coordinator takes over the current Orca terminal and branch.

### What you will see

1. **In Orca:** a worktree and terminal named `orcaducho:coordinator · <objective>`. Shortly after, one terminal and child worktree per task, named `orcaducho:worker · <task>` or `orcaducho:lead · <epic>`.
2. **On GitHub:** an epic issue, with one sub-issue per task tagged by risk. Each worker's 3-sentence result is posted as a comment on its issue.
3. **At the end:** one PR from the run branch to `base` that closes the epic, plus a short per-task report from the coordinator.

### Steering, questions and resuming

- **Questions:** workers never open local prompts. They ask the coordinator through Orca, and the coordinator asks you only for product decisions.
- **Talking to the coordinator:** type into its terminal at any time.
- **Resuming:** if the coordinator's session ends, run `orcaducho start` again in the run worktree's Orca terminal. It resumes from `.orcaducho/plan.md` and Orca's task state without planning again.

## How it works

### Token budget

- **Opus only plans.** It never reads code, diffs, logs or issue threads, only `worker_done` summaries. Codebase facts it needs come from a Haiku `Explore` subagent.
- **Haiku first.** Every task starts on Haiku. After a failed gate the worker gets one fix attempt; if it fails again the task is retried on Sonnet, and then escalated to the coordinator.
- **Deterministic before LLM.** A hook gates `worker_done --outcome succeeded`:

  | risk | gate |
  |---|---|
  | low  | clean tree + `check` |
  | med  | the above + headless Haiku diff review |
  | high | the above + headless Sonnet diff review |

- **Mechanics live in a script.** Worktree and terminal creation, merges, GitHub labels and comments run in `bin/orcaducho`, so no model tokens are spent on them.
- **Short agent prompts,** because every worker pays for its prompt.

### Named agents in Orca

`orca orchestration worker-start --agent claude` only starts plain `claude`, so it cannot pick an agent definition. `orcaducho spawn` therefore:

1. creates the child worktree (`orca worktree create --parent-worktree …`) and names it;
2. opens a terminal titled `orcaducho:<role> · <task>` that runs `claude --agent orcaducho:<role> --model <m> -n "orcaducho:<role> · <task>"`;
3. binds it under supervision with `orca orchestration worker-start --task <id> --terminal <handle>`.

The coordinator also names each Orca Task with `--task-title` and `--display-name`.

Orca treats a terminal bound this way as *external*, so `worker-release` leaves it open. `orcaducho release` runs `worker-release` first, then closes that terminal, and only once the worker has settled.

### Hooks

The hooks are inert unless `ORCADUCHO_ROLE` is set, so your ordinary Claude Code sessions are unaffected.

- **`guard`:** the coordinator may write only `.orcaducho/` and `.orcaducho.json`; a worker may write only its `--owns` globs.
- **`gate`:** the risk-tiered gate described above. After two failures, it tells the worker to report `failed` so the coordinator escalates.
- **`post`:** mirrors each `worker_done` onto the task's GitHub issue.

### State

- **GitHub issues:** durable, human-readable plan and results.
- **Orca Run → Tasks → Dispatches:** what runs, when, and when it is settled.
- **`.orcaducho/plan.md`:** a resume point for the coordinator.

## Command reference

| Command | What it does |
|---|---|
| `orcaducho start [--name <branch>] [--base <ref>] [--model opus] [--effort <lvl>] "<objective>"` | Launch the coordinator (new worktree with `--name`, else in this terminal) |
| `orcaducho spawn --role worker\|lead --task <id> --title "<t>" [--risk low\|med\|high] [--issue <n>] [--owns "<globs>"] [--model <m>] [--effort <lvl>] [--worktree new-child\|current\|<selector>] [--retry-of <dispatch>] [--run <run>]` | Start a named, supervised agent for an Orca Task (prints JSON with `dispatch`, `handle`, `worktree`, `branch`) |
| `orcaducho release --dispatch <id>` | `worker-release`, then close the agent's terminal |
| `orcaducho merge <branch>` | `git merge --no-ff`. Exits 2 and lists the conflicting files if it conflicts (the merge is aborted) |
| `orcaducho issue epic\|task --title "<t>" [--body "<b>"] [--parent <n>] [--risk <r>]` | Create an issue or sub-issue; prints its number, or `-` if issues are off |
| `orcaducho init [--check "<cmd>"] [--base <ref>] [--skip-permissions] [--no-issues] [--force]` | Write `.orcaducho.json` for this repo and exclude `.orcaducho/` locally |
| `orcaducho install [--dir <path>]` | Symlink the CLI onto your PATH |
| `orcaducho hook guard\|gate\|post` | Hook entry points (used by `hooks/hooks.json`) |

## Configuration reference

**`.orcaducho.json`** (repo root):

| Key | Default | Meaning |
|---|---|---|
| `check` | `""` (no checks) | Shell command that must pass before a worker reports success |
| `base` | repo default branch | Base of the run worktree and target of the PR |
| `issues` | `true` | Mirror the plan and results to GitHub issues |
| `claudeArgs` | `["--permission-mode", "acceptEdits"]` | Extra arguments for every orcaducho `claude` session |

**Environment variables:**

| Variable | Meaning |
|---|---|
| `ORCADUCHO_PLUGIN_DIR` | Load the plugin from this checkout (`--plugin-dir`) instead of the installed copy; inherited by child sessions |
| `ORCA_CLI_COMMAND` | Orca executable to use (otherwise `orca`, or `orca-ide` on Linux outside Orca terminals) |
| `ORCADUCHO_ROLE`, `_TASK`, `_RISK`, `_ISSUE`, `_OWNS`, `_BASE`, `_MODEL`, `_READONLY` | Set by `orcaducho spawn` for each session; do not set by hand |

## Troubleshooting

- **A worker sits at a prompt.** It is waiting for a permission or folder-trust prompt. Allow the command in settings (see [Set up a project](#set-up-a-project)), or answer the prompt once in its terminal.
- **`run inside an Orca terminal`.** `orcaducho start` without `--name` needs Orca's terminal environment. Open a terminal in Orca or pass `--name`.
- **Linux:** outside Orca terminals, bare `orca` is the GNOME screen reader. orcaducho uses `orca-ide` there automatically.
- **`nested_worker_depth_exceeded`.** Orca's nesting limit was reached. The lead implements that task itself.
- **An issue number prints `-`.** `gh` is missing or not logged in, Issues are disabled on the repo, or `"issues": false` is set.
- **Workers are blocked by the gate.** The `check` command fails on the base branch too. Fix the base first, or adjust `check`.

## Update and uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/zugazagoitia/orcaducho/main/install.sh | sh -s -- --update
```

or, inside Claude Code:

```
/plugin marketplace update orcaducho
/plugin update orcaducho@orcaducho
```

```
/plugin uninstall orcaducho@orcaducho
/plugin marketplace remove orcaducho
rm ~/.local/bin/orcaducho
```

## Development

```sh
git clone https://github.com/zugazagoitia/orcaducho && cd orcaducho
claude plugin validate .
export ORCADUCHO_PLUGIN_DIR="$PWD"     # bash/zsh; fish: set -gx ORCADUCHO_PLUGIN_DIR $PWD
claude --plugin-dir "$PWD" --agent orcaducho:coordinator
```

**Releasing:** bump `version` in `.claude-plugin/plugin.json` with every change. Claude Code only refreshes an installed plugin when the version changes.

## License

MIT
