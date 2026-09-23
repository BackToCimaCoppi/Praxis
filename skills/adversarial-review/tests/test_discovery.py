import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "discover_bridges.py"
spec = importlib.util.spec_from_file_location("discover_bridges", SCRIPT)
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


class DiscoveryTest(unittest.TestCase):
    def test_missing_bridges_report_unavailable(self):
        with patch.object(discovery.shutil, "which", return_value=None):
            self.assertFalse(discovery.claude()["available"])
            self.assertFalse(discovery.cursor()["available"])
            self.assertFalse(discovery.codex()["available"])

    def test_cursor_filters_auto_and_fast(self):
        def fake_run(args, timeout=35):
            output = "Logged in" if args[-1] == "status" else (
                "auto - Auto (default)\nmodel-high - Strong\nmodel-high-fast - Strong Fast\n")
            return subprocess.CompletedProcess(args, 0, output, "")
        with patch.object(discovery.shutil, "which", return_value="/usr/bin/agent"), \
             patch.object(discovery, "run", side_effect=fake_run):
            models = discovery.cursor()["models"]
        self.assertEqual([m["id"] for m in models], ["model-high"])

    def test_claude_uses_live_aliases_without_account_details(self):
        def fake_run(args, timeout=35):
            output = '{"loggedIn":true,"email":"private@example.test"}' if args[1:3] == ["auth", "status"] else (
                "Current model: `Model`\nUsage: /model <name>. Available: opus, sonnet, best, default, or a full model ID.\n")
            return subprocess.CompletedProcess(args, 0, output, "")
        with patch.object(discovery.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(discovery, "run", side_effect=fake_run):
            result = discovery.claude()
        self.assertEqual([m["id"] for m in result["models"]], ["opus", "sonnet"])
        self.assertNotIn("private@example.test", str(result))


if __name__ == "__main__":
    unittest.main()
