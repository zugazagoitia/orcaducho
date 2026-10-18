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
        self.assertIsNone(od.coordinator_prompt("", {}))
        self.assertIn("authorised", od.coordinator_prompt("do x", {"base": "develop"}))
        self.assertEqual(od.coordinator_prompt("do x", {"autonomous": False}), "do x")


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
