from __future__ import annotations

import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
FLOW = SKILL_ROOT / "references/标准研发流程.md"
FRAGMENTS = SKILL_ROOT / "assets/研发流程模板/阶段片段库"


class StandardFlowTemplateTest(unittest.TestCase):
    def test_unique_eight_stage_order(self) -> None:
        text = FLOW.read_text(encoding="utf-8")
        expected = [
            "① 调查",
            "② 开放探讨",
            "③ 轻量设计",
            "④ 测试用例设计",
            "⑤ 真值收敛与规格冻结",
            "⑥ goal 章程",
            "⑦ goal 执行",
            "⑧ 候选终审",
        ]
        positions = [text.index(item) for item in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertNotRegex(text, r"九阶段(?:动作菜单|流水线|是抽象的)")

    def test_goal_m0_replaces_execution_readiness_stage(self) -> None:
        freeze = (FRAGMENTS / "规格冻结.md").read_text(encoding="utf-8")
        charter = (FRAGMENTS / "goal章程.md").read_text(encoding="utf-8")
        execution = (FRAGMENTS / "goal执行.md").read_text(encoding="utf-8")
        self.assertFalse((FRAGMENTS / "执行准备.md").exists())
        self.assertIn("**阻塞**：T<goal 章程>", freeze)
        self.assertIn("**依赖**：T<规格冻结>, T<测试用例设计>", charter)
        self.assertIn("M0 启动检查", charter)
        self.assertIn("测试脚本/runner/夹具/环境适配/证据工具", execution)
        self.assertIn("不得给逐 AC 签发 Ready 状态", execution)

    def test_final_review_is_read_only_and_routes_to_one_owner(self) -> None:
        text = (FRAGMENTS / "候选终审.md").read_text(encoding="utf-8")
        for required in (
            "全新上下文",
            "产品、测试资产/runner/夹具/环境适配/证据工具 → **同一 goal 执行**",
            "冻结用例语义 / 正式规格 / 业务语义 → **默认热修**",
            "热修不可靠且获相应批准才回退",
            "终审只读，不实施整改",
        ):
            self.assertIn(required, text)
        for forbidden in ("修复后走", "整改后封闭验收", "终审内修复"):
            self.assertNotIn(forbidden, text)

    def test_execution_can_repair_harness_without_weakening_specs(self) -> None:
        text = (FRAGMENTS / "goal执行.md").read_text(encoding="utf-8")
        self.assertIn("允许修测试脚本、runner、夹具、环境适配器和证据工具", text)
        self.assertIn("并按影响面重跑", text)
        self.assertIn("不削弱测试资产", text)

    def test_goal_stops_only_for_three_user_decisions(self) -> None:
        execution = (FRAGMENTS / "goal执行.md").read_text(encoding="utf-8")
        charter = (FRAGMENTS / "goal章程.md").read_text(encoding="utf-8")
        self.assertIn("停机白名单三条", execution)
        self.assertIn("EXECUTION_BLOCKED", execution)
        self.assertNotIn("同一失败 3 次", execution)
        self.assertNotIn("停机只剩白名单四条", charter)

    def test_goal_rehydrates_after_compaction(self) -> None:
        execution = (FRAGMENTS / "goal执行.md").read_text(encoding="utf-8")
        for required in ("自动上下文压缩", "goal 断点", "飞行日志尾部"):
            self.assertIn(required, execution)
        self.assertIn("T{n}-goal断点.json", execution)

    def test_write_scope_fields_are_in_generic_templates(self) -> None:
        templates = [
            SKILL_ROOT / "assets/任务总控模板.md",
            SKILL_ROOT / "assets/拆分模板/子任务包.md",
        ]
        for template in templates:
            text = template.read_text(encoding="utf-8")
            for field in (
                "start_commit",
                "allowed_write_paths",
                "allowed_cross_task_writes",
                "check_write_scope.py",
            ):
                self.assertIn(field, text, f"{template.name} 缺 {field}")


if __name__ == "__main__":
    unittest.main()
