"""Unit tests for the deterministic parts of bin/orcaducho (stdlib only: python3 -m unittest)."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("orcaducho", str(ROOT / "bin" / "orcaducho"))
_spec = importlib.util.spec_from_loader("orcaducho", _loader)
od = importlib.util.module_from_spec(_spec)
_loader.exec_module(od)

SPEC = """Part of #201. Task 5/5: e2e.
Target: new e2e/admin-public-data.spec.ts.
Change: Playwright spec covering the fill flows.
Constraints: don't modify app code.
Ownership: e2e/admin-public-data.spec.ts, e2e/support/**
Acceptance: pnpm typecheck && pnpm lint pass; e2e green on all projects; pnpm size green."""


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            fn(*args)
        except SystemExit:
            pass
    text = out.getvalue().strip()
    return json.loads(text) if text else None


class Repo:
    """A throwaway git repo to run hooks against."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.path)], check=True)
        return self.path

    def __exit__(self, *exc):
        self.tmp.cleanup()


class GlobTest(unittest.TestCase):
    def test_globs(self):
        self.assertTrue(od.glob_re("e2e/support/**").match("e2e/support/api/x.ts"))
        self.assertTrue(od.glob_re("src/**/*.vue").match("src/App.vue"))
        self.assertFalse(od.glob_re("src/*.ts").match("src/a/b.ts"))


class SpecRenderTest(unittest.TestCase):
    def test_parse(self):
        intro, sections = od.parse_spec(SPEC)
        self.assertEqual(intro, "Part of #201. Task 5/5: e2e.")
        self.assertEqual(set(sections), {"Target", "Change", "Constraints", "Ownership", "Acceptance"})
        self.assertEqual(sections["Change"], "Playwright spec covering the fill flows.")

    def test_render_task_spanish(self):
        body = od.render_task(SPEC, "med", "201", {"lang": "es"})
        self.assertIn("> Tarea de orcaducho · riesgo 🟡 medio · parte de #201", body)
        self.assertIn("### Qué hay que hacer\nPlaywright spec covering the fill flows.", body)
        self.assertIn("- `e2e/support/**`", body)
        self.assertIn("- [ ] e2e green on all projects", body)
        self.assertIn("<details>", body)
        self.assertIn(SPEC, body)  # agents keep the spec verbatim
        self.assertLess(body.index("Qué hay que hacer"), body.index("Dónde"))

    def test_unstructured_body_is_left_alone(self):
        self.assertEqual(od.render_task("just text", "low", None, {}), "just text")

    def test_fence_survives_tildes(self):
        self.assertTrue(od.fenced("a ~~~ b").startswith("~~~~text"))

    def test_epic(self):
        body = od.render_epic("T1 ...\nT2 ...", "Fill the grid from public data.", {"lang": "en"})
        self.assertIn("### Goal\nFill the grid from public data.", body)
        self.assertIn("<summary>🤖 Plan as the coordinator wrote it</summary>", body)
        self.assertNotIn("<details>", od.render_epic("plain plan", None, {}))

    def test_result_comment(self):
        body = od.render_result("worker", "succeeded", "Add spec", "Did it.", "haiku", {"lang": "en"})
        self.assertTrue(body.startswith("### ✅ worker · succeeded"))
        self.assertIn("<sub>orcaducho · haiku</sub>", body)


class AutonomyHookTest(unittest.TestCase):
    def run_hook(self, role, fn, event, cfg=None):
        with Repo() as repo, mock.patch.dict(os.environ, {"ORCADUCHO_ROLE": role}):
            if cfg is not None:
                (repo / ".orcaducho.json").write_text(json.dumps(cfg))
            event = {"cwd": str(repo), **event}
            if callable(event.get("setup")):
                event.pop("setup")(repo)
            return capture(fn, event)

    def test_ask_is_denied_with_route(self):
        out = self.run_hook("worker", od.hook_ask, {"tool_name": "AskUserQuestion"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("`ask`", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_supervised_config_disables_autonomy(self):
        self.assertIsNone(self.run_hook("worker", od.hook_ask, {}, {"autonomous": False}))
        self.assertIsNone(self.run_hook("coordinator", od.hook_permission, {"tool_name": "Bash"}, {"autonomous": False}))

    def test_permission_prompt_is_denied(self):
        out = self.run_hook("coordinator", od.hook_permission, {"tool_name": "Bash"})
        decision = out["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        self.assertIn("plan.md", decision["message"])

    def test_inert_for_other_roles(self):
        self.assertIsNone(self.run_hook("reviewer", od.hook_permission, {"tool_name": "Bash"}))

    def test_stop_keeps_coordinator_going(self):
        out = self.run_hook("coordinator", od.hook_stop, {})
        self.assertIn("Status: done", out["hookSpecificOutput"]["additionalContext"])

    def test_stop_allows_finished_run(self):
        def done(repo):
            (repo / ".orcaducho").mkdir()
            (repo / ".orcaducho" / "plan.md").write_text("Run: r1\nStatus: done\n")
        self.assertIsNone(self.run_hook("coordinator", od.hook_stop, {"setup": done}))

    def test_stop_ignores_workers_and_background_work(self):
        self.assertIsNone(self.run_hook("worker", od.hook_stop, {}))
        self.assertIsNone(self.run_hook("coordinator", od.hook_stop, {"background_tasks": [{"id": "t"}]}))


class GuardTest(unittest.TestCase):
    def test_worker_outside_ownership_is_denied(self):
        with Repo() as repo, mock.patch.dict(os.environ, {"ORCADUCHO_ROLE": "worker", "ORCADUCHO_OWNS": "src/**"}):
            out = capture(od.hook_guard, {"cwd": str(repo), "tool_input": {"file_path": str(repo / "README.md")}})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIsNone(capture(od.hook_guard, {"cwd": str(repo), "tool_input": {"file_path": str(repo / "src/a.ts")}}))


class InitTest(unittest.TestCase):
    def test_detect_check(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest", "lint": "eslint", "dev": "vite"}}))
            (root / "pnpm-lock.yaml").write_text("")
            self.assertEqual(od.detect_check(root), "pnpm lint && pnpm test")
            (root / "pnpm-lock.yaml").unlink()
            self.assertEqual(od.detect_check(root), "npm run lint && npm run test")

    def test_default_args_use_auto_mode(self):
        argv = od.claude_argv("worker", "haiku", None, "n", {}, {**od.config(), "advisor": "opus"})
        self.assertIn("auto", argv)
        self.assertEqual(argv[argv.index("--advisor") + 1], "opus")
        self.assertNotIn("--advisor", od.claude_argv("coordinator", "opus", None, "n", {}, {**od.config(), "advisor": "opus"}))

    def test_coordinator_prompt(self):
        self.assertTrue(od.coordinator_prompt("", {}).startswith(od.RESUME))
        self.assertIn("authorised", od.coordinator_prompt("do x", {"base": "develop"}))
        self.assertNotIn("authorised", od.coordinator_prompt("do x", {"autonomous": False}))

    def test_prompt_follows_ship_and_depth_policy(self):
        local = od.coordinator_prompt("do x", {"ship": "local", "todo": "markdown"})
        self.assertIn("do not push", local)
        self.assertNotIn("create the planned issues", local)
        auto = od.coordinator_prompt("do x", {"ship": "pr-draft", "autoMerge": True, "todo": "issues"})
        self.assertIn("draft PR", auto)
        drain = od.coordinator_prompt("do x", {"depth": "drain", "maxItems": 2, "todo": "issues"}, drain=1)
        self.assertIn("fewer than 2", drain)
        self.assertIn("--drain 2", drain)

    def test_workers_and_reviewer_start_lean(self):
        cfg = od.config()
        worker = od.claude_argv("worker", "haiku", None, "n", {}, cfg)
        for flag in ("--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "--plugin-dir"):
            self.assertIn(flag, worker)
        self.assertEqual(worker[worker.index("--setting-sources") + 1], "project,local")
        self.assertNotIn("--strict-mcp-config", od.claude_argv("coordinator", "opus", None, "n", {}, cfg))
        self.assertNotIn("--strict-mcp-config", od.claude_argv("worker", "haiku", None, "n", {}, {**cfg, "isolate": False}))

    def test_parse_setting(self):
        self.assertEqual(od.parse_setting("autoMerge=true"), ("autoMerge", True))
        self.assertEqual(od.parse_setting("maxItems=5"), ("maxItems", 5))
        self.assertEqual(od.parse_setting("claudeArgs=--a b"), ("claudeArgs", ["--a", "b"]))
        for bad in ("depth=forever", "nope=1", "autoMerge=yes", "maxItems=x", "check"):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    od.parse_setting(bad)

    def test_init_set_merges_and_validates(self):
        with Repo() as repo, chdir(repo):
            (repo / ".orcaducho.json").write_text(json.dumps({"check": "make test", "issues": False}))
            capture(od.cmd_init, init_args(set=["depth=plan", "ship=local"]))
            cfg = json.loads((repo / ".orcaducho.json").read_text())
            self.assertEqual((cfg["check"], cfg["todo"], cfg["depth"], cfg["ship"]), ("make test", "none", "plan", "local"))
            self.assertNotIn("issues", cfg)
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                od.cmd_init(init_args(set=["depth=drain"]))

    def test_init_with_flags_is_not_interactive(self):
        with Repo() as repo, chdir(repo), mock.patch.object(od.os, "execvp") as ex:
            capture(od.cmd_init, init_args(todo="markdown", check="true"))
            ex.assert_not_called()
            self.assertEqual(json.loads((repo / ".orcaducho.json").read_text())["todo"], "markdown")


def init_args(**kw):
    a = dict(check=None, base=None, lang=None, advisor=None, todo=None, depth=None, max_items=None, ship=None,
             no_issues=False, supervised=False, skip_permissions=False, auto_merge=False, no_isolate=False,
             force=False, yes=False, set=None, detect=False)
    a.update(kw)
    return od.argparse.Namespace(**a)


@contextlib.contextmanager
def chdir(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


# A throwaway identity, and no commit signing from the developer's global git config.
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false"}


def commit_all(repo):
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"], check=True)


class MarkdownStoreTest(unittest.TestCase):
    def test_epic_task_and_done(self):
        with Repo() as repo, chdir(repo), mock.patch.dict(os.environ, GIT_ENV):
            os.environ.pop("ORCADUCHO_ROLE", None)
            commit_all(repo)
            (repo / ".orcaducho.json").write_text(json.dumps({"todo": "markdown"}))
            issue = lambda **kw: od.argparse.Namespace(**{"title": "t", "body": "", "goal": None, "parent": None,
                                                         "risk": "low", **kw})
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                od.cmd_issue(issue(kind="epic", title="Rate limit", goal="Stop brute force."))
                od.cmd_issue(issue(kind="task", title="Add limiter", parent="E1", risk="med",
                                   body="Target: src/auth.ts::login\nChange: x"))
                od.cmd_issue(issue(kind="task", title="Docs", parent="E1"))
            self.assertEqual(out.getvalue().split(), ["E1", "T1", "T2"])
            body = (repo / "BACKLOG.md").read_text()
            self.assertIn("### E1 · Rate limit\n\nStop brute force.\n- [ ] T1 · Add limiter · risk med · src/auth.ts::login\n- [ ] T2", body)
            capture(od.cmd_done, od.argparse.Namespace(ref="T1", failed=False))
            capture(od.cmd_done, od.argparse.Namespace(ref="T2", failed=True))
            body = (repo / "BACKLOG.md").read_text()
            self.assertIn("- [x] T1 ·", body)
            self.assertIn("- [!] T2 ·", body)
            log = subprocess.run(["git", "log", "--oneline"], capture_output=True, text=True).stdout
            self.assertIn("backlog: T2 failed", log)

    def test_target_without_path_warns(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            od.warn_unnamed_target("Target: the login thing\nChange: x")
        self.assertIn("path::symbol", err.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            od.warn_unnamed_target("Target: src/auth/login.ts::login")
        self.assertEqual(err.getvalue(), "")

    def test_backlog_next_take_add(self):
        with Repo() as repo, chdir(repo):
            (repo / ".orcaducho.json").write_text(json.dumps({"todo": "markdown"}))
            (repo / "BACKLOG.md").write_text("# Backlog\n\n## Todo\n- [ ] first\n- [x] old\n\n## Runs\n- [ ] T1 · not a todo\n")
            nxt = capture(od.cmd_backlog, od.argparse.Namespace(action="next", ref=None))
            self.assertEqual(nxt["title"], "first")
            capture(od.cmd_backlog, od.argparse.Namespace(action="add", ref="second"))
            capture(od.cmd_backlog, od.argparse.Namespace(action="take", ref=nxt["ref"]))
            self.assertEqual(capture(od.cmd_backlog, od.argparse.Namespace(action="next", ref=None))["title"], "second")
            self.assertIn("- [ ] first\n- [x] old\n- [ ] second\n", (repo / "BACKLOG.md").read_text())

    def test_ship_local_ticks_backlog_item(self):
        with Repo() as repo, chdir(repo), mock.patch.dict(os.environ, GIT_ENV):
            commit_all(repo)
            (repo / ".orcaducho.json").write_text(json.dumps({"todo": "markdown", "ship": "local"}))
            (repo / "BACKLOG.md").write_text("# Backlog\n\n## Todo\n- [ ] first\n")
            ref = od.todo_items((repo / "BACKLOG.md").read_text())[0][0]
            with mock.patch.dict(os.environ, {"ORCADUCHO_ITEM": ref}):
                out = capture(od.cmd_ship, od.argparse.Namespace(title="t", body=""))
            self.assertFalse(out["pushed"])
            self.assertIn("- [x] first", (repo / "BACKLOG.md").read_text())


class RotationAndCostTest(unittest.TestCase):
    def test_wave_checkpoint_rotates_coordinator(self):
        with Repo() as repo, mock.patch.dict(os.environ, {"ORCADUCHO_ROLE": "coordinator", "ORCA_TERMINAL_HANDLE": "term_1"}), \
                mock.patch.object(od, "detach") as popen:
            (repo / ".orcaducho").mkdir()
            plan = repo / ".orcaducho" / "plan.md"
            plan.write_text("Run: r1\nCheckpoint: wave\n")
            self.assertIsNone(capture(od.hook_stop, {"cwd": str(repo)}))
            self.assertEqual(plan.read_text(), "Run: r1\n")
            self.assertIn("rotate", popen.call_args[0][0])
            popen.reset_mock()
            out = capture(od.hook_stop, {"cwd": str(repo)})  # no checkpoint: keep looping
            popen.assert_not_called()
            self.assertIn("Status: done", out["hookSpecificOutput"]["additionalContext"])

    def test_paused_and_awaiting_approval_end_the_loop(self):
        with Repo() as repo:
            (repo / ".orcaducho").mkdir()
            for status in ("paused", "awaiting-approval"):
                (repo / ".orcaducho" / "plan.md").write_text(f"Status: {status}\n")
                self.assertTrue(od.run_finished(str(repo)))

    def test_session_registry_and_cost(self):
        with Repo() as repo, chdir(repo), mock.patch.dict(os.environ, {"ORCADUCHO_ROLE": "worker", "ORCADUCHO_MODEL": "haiku"}):
            t = repo / "t.jsonl"
            msg = lambda i, n: json.dumps({"type": "assistant", "message": {"id": i, "model": "claude-haiku",
                                           "usage": {"input_tokens": n, "cache_read_input_tokens": 10 * n, "output_tokens": 1}}})
            t.write_text("\n".join([msg("a", 1), msg("a", 1), msg("b", 2), "{bad"]) + "\n")
            (repo / "t" / "subagents").mkdir(parents=True)
            (repo / "t" / "subagents" / "s.jsonl").write_text(msg("c", 3) + "\n")
            od.hook_session({"cwd": str(repo), "session_id": "s1", "transcript_path": str(t), "source": "startup"})
            od.hook_session({"cwd": str(repo), "session_id": "s1", "transcript_path": str(t), "source": "resume"})
            rows = capture(od.cmd_cost, od.argparse.Namespace(hours=None, json=True))
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["role"], rows[0]["sessions"], rows[0]["input_tokens"]), ("worker", 1, 6))
            self.assertEqual(rows[0]["total"], 6 + 60 + 3)


class UpdateTest(unittest.TestCase):
    def test_enable_auto_update_keeps_other_settings(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": d}):
            f = Path(d) / "settings.json"
            f.write_text(json.dumps({"model": "opus", "extraKnownMarketplaces": {"other": {"x": 1}}}))
            self.assertTrue(od.enable_auto_update())
            data = json.loads(f.read_text())
            self.assertEqual(data["model"], "opus")
            self.assertEqual(data["extraKnownMarketplaces"]["other"], {"x": 1})
            self.assertTrue(data["extraKnownMarketplaces"]["orcaducho"]["autoUpdate"])
            self.assertEqual(data["extraKnownMarketplaces"]["orcaducho"]["source"]["repo"], "zugazagoitia/orcaducho")

    def test_unparseable_settings_are_left_alone(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": d}):
            (Path(d) / "settings.json").write_text("{not json")
            self.assertFalse(od.enable_auto_update())
            self.assertEqual((Path(d) / "settings.json").read_text(), "{not json")

    def test_maybe_update_is_throttled(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": d}), \
                mock.patch.object(od, "update_now") as upd, mock.patch.object(od.shutil, "which", return_value="/bin/claude"):
            os.environ.pop("ORCADUCHO_PLUGIN_DIR", None)
            os.environ.pop("ORCADUCHO_NO_UPDATE", None)
            stamp = Path(d) / "plugins" / "data" / "orcaducho-orcaducho" / "last-update-check"
            stamp.parent.mkdir(parents=True)
            stamp.write_text(str(int(od.time.time())))
            od.maybe_update()
            upd.assert_not_called()
            stamp.write_text("0")
            upd.return_value = {"ok": True, "from": "1", "to": "1"}
            od.maybe_update()
            upd.assert_called_once()

    def test_maybe_update_skips_dev_checkouts(self):
        with mock.patch.dict(os.environ, {"ORCADUCHO_PLUGIN_DIR": "/x"}), mock.patch.object(od, "update_now") as upd:
            od.maybe_update()
            upd.assert_not_called()


if __name__ == "__main__":
    unittest.main()
