---
name: orcaducho
description: Start or resume an orcaducho multi-agent run on Orca — an Opus coordinator plans the objective into GitHub issues and Orca Tasks and dispatches named Sonnet leads and Haiku-first workers. Use when the user types /orcaducho or asks to run a task "with orcaducho".
argument-hint: "<objective> [--name <run-branch>]"
---

Launch the coordinator. Do not plan or implement the objective yourself, since that would spend this session's tokens.

1. Pick a short kebab-case run name from the objective (e.g. `orcaducho/add-login-rate-limit`), unless the user passed `--name`.
2. Run exactly:
   ```
   orcaducho start --name "<run name>" "<objective>"
   ```
   The plugin puts `orcaducho` on the Bash tool's PATH. If it is still not found, use `python3 "${CLAUDE_PLUGIN_ROOT}/bin/orcaducho"` instead.
   The command creates a run worktree and an Orca terminal titled `orcaducho:coordinator · …`, running `claude --agent orcaducho:coordinator --model opus` in auto mode. The run is unattended: the coordinator and its agents decide on their own and never wait for the user.
3. Reply in at most two lines: the worktree and terminal handle it printed, and that progress is visible in Orca and on the epic issue.

To resume a run, open the coordinator's terminal in Orca. If it was closed, run `orcaducho start` from inside the run worktree's Orca terminal; the coordinator resumes from `.orcaducho/plan.md`.
