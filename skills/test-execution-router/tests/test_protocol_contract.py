from __future__ import annotations

import unittest
from pathlib import Path


SKILLS = Path(__file__).resolve().parents[2]


def read(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


class ProtocolContractTest(unittest.TestCase):
    def test_router_has_bootstrap_and_verification_modes(self) -> None:
        text = read("test-execution-router")
        self.assertIn("`bootstrap` M0 启动检查", text)
        self.assertIn("`verification` 正式验证", text)
        self.assertIn("HEALTHY / REPAIRED / BLOCKED_AUTH / MANUAL_BOUNDARY", text)
        self.assertIn("不得逐 AC 预演或签发 Ready", text)
        self.assertIn("同一 goal 内修复", text)

    def test_all_eight_surfaces_are_explicit(self) -> None:
        text = read("test-execution-router")
        surfaces = (
            "单元",
            "接口",
            "DB 预置",
            "DB 终态",
            "Web/admin UI",
            "小程序 UI",
            "视觉",
            "手工",
        )
        marker = next(line for line in text.splitlines() if "已生成执行面矩阵" in line)
        for surface in surfaces:
            self.assertIn(surface, marker)
        self.assertIn("本任务命中面各一行", marker)

    def test_evidence_chain_is_one_way_and_content_addressed(self) -> None:
        router = read("test-execution-router")
        charter = read("goal-charter")
        for text in (router, charter):
            self.assertIn("raw", text)
            self.assertIn("采集时不可变信封", text)
            self.assertIn("AC 映射", text)
            self.assertIn("状态账本", text)
            self.assertIn("同一内容寻址包", text)
        for forbidden in ("状态账本自证", "反向改 raw", "事后补绑"):
            self.assertIn(forbidden, router)

    def test_assertion_native_evidence_rejects_proxy_green(self) -> None:
        router = read("test-execution-router")
        cases = read("test-case-design")
        standards = read("test-standards")
        for required in (
            "evidence_semantics_version: assertion-native-v1",
            "framework_test_id",
            "消费者完整性",
            "观测分布报告",
            "supporting_only_reason",
        ):
            self.assertIn(required, router)
        for proxy in ("套件退出码", "日志/聚合哈希"):
            self.assertIn(proxy, router)
        self.assertIn("证明部件覆盖表", cases)
        self.assertIn("不另建 observation contract", cases)
        self.assertIn("原生观测事件", standards)

    @unittest.skipUnless((SKILLS / "plan-goal" / "SKILL.md").exists(), "plan-goal skill 未安装（可选依赖）")
    def test_retry_count_is_not_a_user_decision_boundary(self) -> None:
        router = read("test-execution-router")
        charter = read("goal-charter")
        plan = read("plan-goal")
        for text in (router, charter, plan):
            self.assertIn("EXECUTION_BLOCKED", text)
            self.assertNotIn("同一失败点连续 3 次", text)

    def test_manual_requires_physical_boundary(self) -> None:
        standards = read("test-standards")
        cases = read("test-case-design")
        for required in (
            "AI 可控制浏览器/开发者工具",
            "VLM",
            "物理边界证明",
            "人工里程碑",
        ):
            self.assertIn(required, standards)
        self.assertIn("AI 无法操作", cases)
        self.assertIn("GUI", cases)
        self.assertIn("manual_runbook", cases)

    def test_charter_inherits_authorization_and_owns_bootstrap(self) -> None:
        text = read("goal-charter")
        for required in (
            "M0 启动检查",
            "目标环境",
            "精确动作",
            "目标对象",
            "费用上限",
            "副作用范围",
            "不得扩大",
            "执行证据检查器",
        ):
            self.assertIn(required, text)
        self.assertNotIn("测试脚本 →", text)

    def test_execution_ref_is_owned_by_goal_bootstrap(self) -> None:
        text = read("test-case-design")
        self.assertIn("规格冻结阶段可填预定锚点", text)
        self.assertIn("goal 的 M0 负责实现为可运行落点", text)
        self.assertNotIn("测试脚本（施工时产出）", text)


if __name__ == "__main__":
    unittest.main()
