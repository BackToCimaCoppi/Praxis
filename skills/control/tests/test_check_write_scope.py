from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_write_scope.py"


class CheckWriteScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.write("src/target.txt", "base\n")
        self.write("product/app.txt", "base\n")
        self.write("tests/runner.txt", "base\n")
        self.write(
            "control/README.md",
            "# 总控\n\n## 子任务总表\nold\n\n## 进展记录\nold\n\n## 其他\nkeep\n",
        )
        self.write(
            "control/T8-goal执行.md",
            "# T8\n\n## 当前状态\n进行中\n\n## 要做的事情\nkeep\n",
        )
        self.base = self.commit("baseline")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=self.repo, text=True
        ).strip()

    def write(self, relative: str, text: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def check(self, candidate: str, *rules: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--repo",
                str(self.repo),
                "--start-commit",
                self.base,
                "--candidate",
                candidate,
                *rules,
            ],
            text=True,
            capture_output=True,
        )

    def test_allowed_path_passes(self) -> None:
        self.write("src/target.txt", "changed\n")
        candidate = self.commit("allowed")
        result = self.check(candidate, "--allow", "src/**")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_candidate_with_out_of_scope_path_fails(self) -> None:
        self.write("src/target.txt", "changed\n")
        self.write("product/app.txt", "leaked\n")
        candidate = self.commit("mixed")
        result = self.check(candidate, "--allow", "src/**")
        self.assertEqual(result.returncode, 1)
        self.assertIn("越界路径 product/app.txt", result.stdout)

    def test_unrelated_intermediate_commit_is_not_attributed_to_task(self) -> None:
        self.write("product/app.txt", "other task\n")
        self.commit("unrelated")
        self.write("src/target.txt", "task change\n")
        candidate = self.commit("task candidate")
        result = self.check(candidate, "--allow", "src/**")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cross_task_markdown_sections_pass(self) -> None:
        self.write(
            "control/README.md",
            "# 总控\n\n## 子任务总表\nnew\n\n## 进展记录\nnew\n\n## 其他\nkeep\n",
        )
        candidate = self.commit("status only")
        result = self.check(
            candidate,
            "--allow-cross",
            "control/README.md::子任务总表",
            "--allow-cross",
            "control/README.md::进展记录",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cross_task_change_outside_section_fails(self) -> None:
        self.write(
            "control/README.md",
            "# 总控\n\n## 子任务总表\nnew\n\n## 进展记录\nold\n\n## 其他\nchanged\n",
        )
        candidate = self.commit("status and body")
        result = self.check(
            candidate,
            "--allow-cross",
            "control/README.md::子任务总表",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("允许标题之外", result.stdout)

    def test_goal_charter_cannot_modify_product(self) -> None:
        self.write("product/app.txt", "changed by charter\n")
        candidate = self.commit("charter overreach")
        result = self.check(candidate, "--allow", "control/**")
        self.assertEqual(result.returncode, 1)

    def test_final_review_can_only_change_returned_status_section(self) -> None:
        self.write(
            "control/T8-goal执行.md",
            "# T8\n\n## 当前状态\n待完成\n\n## 要做的事情\nkeep\n",
        )
        candidate = self.commit("return pointer")
        result = self.check(
            candidate,
            "--allow-cross",
            "control/T8-goal执行.md::当前状态",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_final_review_cannot_modify_test_asset(self) -> None:
        self.write("tests/runner.txt", "changed by final review\n")
        candidate = self.commit("review overreach")
        result = self.check(candidate, "--allow", "control/**")
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
