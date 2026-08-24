from __future__ import annotations

import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


class NextSubtaskPromptTest(unittest.TestCase):
    def test_prompt_requires_disk_rehydration_after_compaction(self) -> None:
        text = (SKILL / "scripts/next_subtask.py").read_text(encoding="utf-8")
        for required in (
            "自动上下文压缩",
            "第一次写入前",
            "章程",
            "goal 断点",
            "飞行日志尾部",
        ):
            self.assertIn(required, text)

    def test_control_does_not_promote_retry_count_to_user_stop(self) -> None:
        spec = (SKILL / "references/总控规范.md").read_text(encoding="utf-8")
        self.assertIn("失败次数本身永远不是停机或前拉依据", spec)
        self.assertIn("EXECUTION_BLOCKED", spec)


if __name__ == "__main__":
    unittest.main()
