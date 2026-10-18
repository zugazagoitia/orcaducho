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
orcaducho init                                                                              # once per repo
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
   - `/agents` in Claude Code lists `orcaducho:coordinator`, `:lead`, `:worker`, `:reviewer` and `:setup`.

## Set up a project

In each repository, run:

```sh
orcaducho init
```

In a terminal, this starts the **setup agent** (`orcaducho:setup`, Sonnet). It explores the repo, then interviews you, then shows every change it wants to make and waits for your approval:

1. **Run policy:** where tasks are recorded, how far a run goes, how it is delivered, autonomy, `check`, `base` and language (see the table below).
2. **Claude setup**, each item shown as full content or a diff with a one-line reason:
   - a short `CLAUDE.md` (about 1 KB), with long rules moved into skills
   - project skills for the workflows it finds
   - path-scoped `.claude/rules/`
   - `.claude/settings.json` (an allowlist for your check commands, deny rules for vendored and build folders)
3. **Machine report:** `orcaducho audit --measure` shows how many tokens your own skills, plugins and MCP servers add to every call. It never edits `~/.claude`.
4. **Delivery:** the approved files and `.orcaducho.json` are committed on `orcaducho/setup` and delivered as your ship policy says. The setup PR is never auto-merged.

For scripts, CI, or the coordinator (which runs `init` itself when `.orcaducho.json` is missing), use flags or settings instead. Without a terminal, `init` writes defaults:

```sh
orcaducho init --yes                                   # detected defaults, no agent
orcaducho init --todo markdown --depth plan --ship pr-draft --check "make test"
orcaducho init --set autoMerge=true --set depth=drain  # change single settings (validated)
orcaducho init --detect                                # what orcaducho detects, as JSON
```

`--check` is detected from `package.json` scripts (`typecheck`, `lint`, `test`, with the package manager taken from the lockfile), `Cargo.toml`, `go.mod` or `pyproject.toml`; `--base` defaults to origin's default branch. `init` also adds `.orcaducho/` to the repo's local git exclude list.

```json
{
  "check": "pnpm typecheck && pnpm lint && pnpm test",
  "base": "develop",
  "todo": "issues",
  "depth": "objective",
  "maxItems": 3,
  "ship": "pr-ready",
  "autoMerge": false,
  "lang": "es",
  "autonomous": true,
  "isolate": true,
  "advisor": "",
  "claudeArgs": ["--permission-mode", "auto"]
}
```

- **`check`:** your fast verification command. It runs before any worker can report success.
- **`base`:** the branch the run starts from and the final PR targets.
- **`todo`:** where the plan is recorded.
  - `issues`: a GitHub epic with sub-issues. With `gh` logged in, orcaducho creates its labels automatically.
  - `markdown`: a committed `BACKLOG.md`. Tasks are refs like `E1` and `T3`, ticked as they finish.
  - `none`: only the coordinator's `plan.md`.
- **`depth`:** how far a run goes.
  - `plan`: plan, then stop for your approval. Resume with `orcaducho start` or by typing into the coordinator's terminal.
  - `objective`: one objective, one PR.
  - `epic-approval`: pause after each epic.
  - `drain`: after each PR, start the next backlog item, up to `maxItems`. The chain stops at the first failed task or failed review.
- **`ship`:** `pr-ready`, `pr-draft`, or `local` (commit only, no push). **`autoMerge`** turns on GitHub auto-merge (squash) for a ready PR once checks pass.
- **Autonomy:** runs are unattended by default (see [Autonomy](#autonomy)). Every session starts in auto mode, where a classifier approves routine actions. `--skip-permissions` uses `--dangerously-skip-permissions` instead; use it only in a container or VM. `--supervised` (`"autonomous": false`) turns the autonomy hooks off.
- **`isolate`:** on by default. Workers, leads and the reviewer start without your user skills, plugins, hooks and MCP servers (see [Token budget](#token-budget)). Turn it off with `--no-isolate` if your workers need something from your user settings, such as an `apiKeyHelper`.
- **`advisor`:** an advisor model (e.g. `opus`) passed as `--advisor` to leads and workers, so a Haiku worker can consult Opus at decision points instead of failing and being retried. Experimental, Anthropic API only.
- **`lang`:** `en` or `es`, the language of issue headings and comments.

`.orcaducho/` holds the coordinator's resumable plan. `orcaducho init` keeps it out of git; if you skipped `init`, add it to `.gitignore`.

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
2. **On GitHub:** an epic issue, with one sub-issue per task tagged by risk. Each task issue is written for humans (what to do, where, files it may change, a checklist of acceptance criteria), with the agent's compact spec kept verbatim in a collapsed block. Each worker's 3-sentence result is posted as a comment on its issue.
3. **At the end:** one review of the whole run branch, then delivery as your `ship` policy says (by default one PR from the run branch to `base` that closes the epic and the task issues), plus a short per-task report from the coordinator. With `todo: markdown` the plan lives in `BACKLOG.md` instead of GitHub issues.

### Steering, questions and resuming

- **Questions:** nobody is asked. Workers ask the coordinator through Orca; the coordinator decides product questions itself, records them on the epic as "to confirm" and lists them in the PR.
- **Talking to the coordinator:** type into its terminal at any time.
- **Resuming:** if the coordinator's session ends, run `orcaducho start` again in the run worktree's Orca terminal. It resumes from `.orcaducho/plan.md` and Orca's task state without planning again. With `depth: plan` or `epic-approval`, resuming (or typing "continue" into its terminal) is the approval.
- **Cost:** `orcaducho cost` prints the tokens each role and model used.

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
- **Isolated sessions.** Every call re-sends the session's base context, so its size multiplies across every call of every agent. Workers, leads and the reviewer start with `--strict-mcp-config --disable-slash-commands --setting-sources project,local` and load orcaducho with `--plugin-dir`. They keep the project's own `.mcp.json`, skills and settings. Measured on a bare call: about 25k tokens down to 10k, and a whole Haiku diff review costs about 3.7k.
- **The coordinator restarts each wave.** After it starts a wave it writes `Checkpoint: wave` to `plan.md` and ends its turn. The `stop` hook then types `/clear` and a resume prompt into its own Orca terminal, so later waves do not pay for the history of earlier ones. It is the same terminal, and you can still type into it.
- **Specs name the code.** Explore reports file paths and symbols, and every `Target:` is written as `path::symbol`; `orcaducho issue` warns when it is not. Named targets get right answers far more often than vague ones.
- **Measure it.** `orcaducho cost` sums real token usage per role and model from the session transcripts (subagents included).

### Named agents in Orca

`orca orchestration worker-start --agent claude` only starts plain `claude`, so it cannot pick an agent definition. `orcaducho spawn` therefore:

1. creates the child worktree (`orca worktree create --parent-worktree …`) and names it;
2. opens a terminal titled `orcaducho:<role> · <task>` that runs `claude --agent orcaducho:<role> --model <m> -n "orcaducho:<role> · <task>"`;
3. binds it under supervision with `orca orchestration worker-start --task <id> --terminal <handle>`.

The coordinator also names each Orca Task with `--task-title` and `--display-name`.

Orca treats a terminal bound this way as *external*, so `worker-release` leaves it open. `orcaducho release` runs `worker-release` first, then closes that terminal, and only once the worker has settled.

### Autonomy

A run never waits for you. Four layers make sure of it:

1. **Auto mode** for every session (`claudeArgs`). Plugin agents cannot set `permissionMode` in their frontmatter, so the mode comes from the launch flag.
2. **Permission prompts are answered.** If something would still prompt (auto mode falls back to prompting after repeated classifier blocks, protected paths, `ask` rules), the `permission` hook denies it and tells the agent how to proceed: workers report through Orca, the coordinator records it as blocked and continues.
3. **No questions to the user.** `AskUserQuestion` is disallowed for every role, and the `ask` hook denies it with the right escalation route.
4. **The coordinator keeps going.** The `stop` hook continues the coordinator's loop until `.orcaducho/plan.md` contains `Status: done` (or `Status: stopped`). `orcaducho start` also writes the user's standing authorisation (create issues, push the run branches, open the PR) into the first prompt, since auto mode reads approvals from the conversation.

Failed tasks escalate Haiku → Sonnet → Opus. If Opus fails too, the task is labelled `status:failed`, its dependants are skipped, and the rest of the run continues.

### Hooks

The hooks are inert unless `ORCADUCHO_ROLE` is set, so your ordinary Claude Code sessions are unaffected.

- **`guard`:** the coordinator may write only `.orcaducho/` and `.orcaducho.json`; a worker may write only its `--owns` globs.
- **`gate`:** the risk-tiered gate described above. After two failures, it tells the worker to report `failed` so the coordinator escalates.
- **`post`:** mirrors each `worker_done` onto the task's GitHub issue as a readable comment.
- **`ask`, `permission`, `stop`:** the autonomy layers above; off with `"autonomous": false`. `stop` also runs the wave restart.
- **`session`:** records each orcaducho session and its transcript in `.git/orcaducho/sessions.jsonl` for `orcaducho cost`.

### State

- **GitHub issues:** durable, human-readable plan and results.
- **Orca Run → Tasks → Dispatches:** what runs, when, and when it is settled.
- **`.orcaducho/plan.md`:** a resume point for the coordinator.

## Command reference

| Command | What it does |
|---|---|
| `orcaducho start [--name <branch>] [--base <ref>] [--model opus] [--effort <lvl>] [--item <ref>] "<objective>"` | Launch the coordinator (new worktree with `--name`, else in this terminal) |
| `orcaducho spawn --role worker\|lead --task <id> --title "<t>" [--risk low\|med\|high] [--issue <n>] [--owns "<globs>"] [--model <m>] [--effort <lvl>] [--worktree new-child\|current\|<selector>] [--retry-of <dispatch>] [--run <run>]` | Start a named, supervised agent for an Orca Task (prints JSON with `dispatch`, `handle`, `worktree`, `branch`) |
| `orcaducho release --dispatch <id>` | `worker-release`, then close the agent's terminal |
| `orcaducho merge <branch>` | `git merge --no-ff`. Exits 2 and lists the conflicting files if it conflicts (the merge is aborted) |
| `orcaducho review [--base <ref>] [--model sonnet]` | One headless review of the whole run branch against its base; exits 3 on FAIL |
| `orcaducho issue epic\|task --title "<t>" [--body "<b>"] [--goal "<g>"] [--parent <n>] [--risk <r>]` | Create an issue or sub-issue; prints its number, or `-` if issues are off. A task `--body` with `Target:`/`Change:`/`Constraints:`/`Ownership:`/`Acceptance:` labels is rendered for humans; an epic `--goal` is shown and `--body` collapsed |
| `orcaducho refresh <n>...` | Re-render task issues created as raw specs by orcaducho < 0.4 |
| `orcaducho init` | In a terminal: the interactive setup agent (policy, CLAUDE.md, skills, rules, settings; lands on `orcaducho/setup`) |
| `orcaducho init [--yes] [--check "<cmd>"] [--base <ref>] [--todo issues\|markdown\|none] [--depth plan\|objective\|epic-approval\|drain] [--max-items <n>] [--ship pr-ready\|pr-draft\|local] [--auto-merge] [--lang en\|es] [--advisor <model>] [--skip-permissions] [--supervised] [--no-isolate] [--force]` | Write `.orcaducho.json` without the agent |
| `orcaducho init --set key=value [--set …]` / `--detect` | Change single settings (validated) / print detected defaults and the project's Claude setup |
| `orcaducho done <ref> [--failed]` | Mark a task finished: tick it in `BACKLOG.md`, or label a failed issue `status:failed` |
| `orcaducho backlog next\|take <ref>\|add "<objective>"` | The queue `depth: drain` works through (issues labelled `backlog`, or `## Todo` in `BACKLOG.md`) |
| `orcaducho ship --title "<t>" [--body "<b>"]` | Deliver the run branch as the policy says: push and open a ready or draft PR, enable auto-merge, or keep it local |
| `orcaducho cost [--hours <n>] [--json]` | Token usage of this repo's orcaducho sessions, by role and model |
| `orcaducho audit [--measure]` | Report what inflates every session's base context; `--measure` compares a bare call with and without your skills and MCP servers (two Haiku calls) |
| `orcaducho update [--auto-only]` | Update the plugin and CLI now, and turn on background auto-update (`--auto-only`: only the latter) |
| `orcaducho install [--dir <path>]` | Symlink the CLI onto your PATH |
| `orcaducho hook guard\|gate\|post\|ask\|permission\|stop` | Hook entry points (used by `hooks/hooks.json`) |

## Configuration reference

**`.orcaducho.json`** (repo root):

| Key | Default | Meaning |
|---|---|---|
| `check` | `""` (no checks) | Shell command that must pass before a worker reports success |
| `base` | repo default branch | Base of the run worktree and target of the PR |
| `todo` | `issues` | `issues`, `markdown` (`BACKLOG.md`) or `none`. Configs from before 0.6 with `"issues": false` read as `none` |
| `depth` | `objective` | `plan`, `objective`, `epic-approval` or `drain` |
| `maxItems` | `3` | `drain`: backlog items per chain |
| `ship` | `pr-ready` | `pr-ready`, `pr-draft` or `local` |
| `autoMerge` | `false` | Enable GitHub auto-merge on a ready PR |
| `lang` | `en` | Language of issue headings and comments (`en`, `es`) |
| `autonomous` | `true` | Deny questions and permission prompts, and keep the coordinator looping until the run is done |
| `isolate` | `true` | Start workers, leads and the reviewer without user skills, plugins, hooks and MCP servers |
| `advisor` | `""` (off) | Advisor model for leads and workers (`--advisor`) |
| `claudeArgs` | `["--permission-mode", "auto"]` | Extra arguments for every orcaducho `claude` session |

**Environment variables:**

| Variable | Meaning |
|---|---|
| `ORCADUCHO_PLUGIN_DIR` | Load the plugin from this checkout (`--plugin-dir`) instead of the installed copy; inherited by child sessions |
| `ORCADUCHO_NO_UPDATE` | Skip the daily update check in `orcaducho start` |
| `ORCA_CLI_COMMAND` | Orca executable to use (otherwise `orca`, or `orca-ide` on Linux outside Orca terminals) |
| `ORCADUCHO_ROLE`, `_TASK`, `_RISK`, `_ISSUE`, `_OWNS`, `_BASE`, `_MODEL`, `_READONLY`, `_DRAIN`, `_ITEM` | Set by `orcaducho spawn` for each session; do not set by hand |

## Troubleshooting

- **A worker sits at a prompt.** Check `.orcaducho.json`: an explicit `"claudeArgs": ["--permission-mode", "acceptEdits"]` (the old default written by `orcaducho init` < 0.4) overrides auto mode; delete the key or rerun `orcaducho init --force`. A folder-trust dialog in a new worktree is not a permission prompt, so no hook can answer it; answer it once in that terminal.
- **`run inside an Orca terminal`.** `orcaducho start` without `--name` needs Orca's terminal environment. Open a terminal in Orca or pass `--name`.
- **Linux:** outside Orca terminals, bare `orca` is the GNOME screen reader. orcaducho uses `orca-ide` there automatically.
- **`nested_worker_depth_exceeded`.** Orca's nesting limit was reached. The lead implements that task itself.
- **An issue number prints `-`.** `gh` is missing or not logged in, Issues are disabled on the repo, or `"issues": false` is set.
- **An isolated worker cannot authenticate or misses a tool.** Isolated sessions skip your user settings (for example an `apiKeyHelper`) and your MCP servers. Put what the project needs in its own `.claude/settings.json` or `.mcp.json`, or set `"isolate": false`.
- **The coordinator does not restart after a wave.** The restart needs the coordinator's Orca terminal (`ORCA_TERMINAL_HANDLE`). Without it, the `stop` hook removes the checkpoint and the coordinator simply continues.
- **Workers are blocked by the gate.** The `check` command fails on the base branch too. Fix the base first, or adjust `check`.

## Update and uninstall

orcaducho keeps itself up to date:

- **Background auto-update.** `install.sh` (or `orcaducho update`) sets `extraKnownMarketplaces.orcaducho.autoUpdate` in `~/.claude/settings.json`; Claude Code has this off by default for third-party marketplaces. Claude Code then refreshes the plugin in the background during sessions, and new sessions load the new version.
- **Daily check before a run.** `orcaducho start` updates at most once every 24 hours before launching the coordinator, and reruns itself if the version changed, so a new run always starts on the latest release. Set `ORCADUCHO_NO_UPDATE=1` to skip it. It is also skipped when `ORCADUCHO_PLUGIN_DIR` points at a development checkout.

The `orcaducho` CLI is a symlink into the marketplace checkout, so it updates together with the plugin. Sessions already running keep the version they loaded.

To update right away:

```sh
orcaducho update
```

or:

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
claude plugin validate --strict .
python3 -m unittest discover -s tests
export ORCADUCHO_PLUGIN_DIR="$PWD"     # bash/zsh; fish: set -gx ORCADUCHO_PLUGIN_DIR $PWD
claude --plugin-dir "$PWD" --agent orcaducho:coordinator
```

**Releasing:** bump `version` in `.claude-plugin/plugin.json` with every change. Claude Code only refreshes an installed plugin when the version changes.

## License

MIT
