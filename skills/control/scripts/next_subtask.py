#!/usr/bin/env python3
"""
选择目标总控的下一个可执行子任务。

优先级：
1. 状态为 进行中 的子任务（恢复未完成工作）
2. 状态为 待完成 且所有依赖均为 已完成 / 已取消 的子任务（按编号顺序）

无可执行子任务时输出阻塞原因。
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    PROJECT_ROOT,
    CONTROL_ROOT,
    list_active_task_dirs,
    find_main_doc,
    read_active_control,
    is_parent_seq,
    is_child_seq,
    expand_dep_to_leaves,
    find_subtask_md,
)


@dataclass
class Subtask:
    seq: str
    name: str
    mode: str
    status: str
    deps: str
    output: str

    @property
    def dep_list(self) -> list[str]:
        if not self.deps or self.deps in {"无", "-", "—"}:
            return []
        return [d.strip() for d in re.split(r"[、,，/\s]+", self.deps) if d.strip()]


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def find_task_dir(keyword: str | None) -> Path:
    """选择目标任务目录。优先级：keyword > active-control 文件 > 唯一候选。

    worktree 不绑定任务，命名约定纯粹是人类可读性建议。
    多激活时通过 .claude/local/active-control 显式指定（每个 worktree 独立）。
    """
    candidates = list_active_task_dirs()
    if not candidates:
        raise SystemExit(
            f"未发现活跃总控目录（{CONTROL_ROOT.relative_to(PROJECT_ROOT)} 下没有含 README.md 的子目录）。\n"
            f"提示：先运行 bootstrap_project.py 初始化骨架，再用 task-control-doc skill 创建任务。"
        )

    if keyword:
        key = normalize(keyword)
        matched = [d for d in candidates if key in normalize(d.name)]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            names = "\n  ".join(d.name for d in matched)
            raise SystemExit(f"匹配多个任务目录，请补关键词：\n  {names}")
        raise SystemExit(f"未匹配关键词 '{keyword}' 的任务")

    active = read_active_control()
    if active:
        matched = [d for d in candidates if d.name == active]
        if matched:
            return matched[0]
        print(
            f"⚠ active-control 文件指向 '{active}'，但未找到匹配的活跃任务（可能已归档或重命名）。\n"
            f"  请检查 .claude/local/active-control 或运行 set_active.py --clear 清除。",
            file=sys.stderr,
        )

    if len(candidates) == 1:
        return candidates[0]

    names = "\n  ".join(d.name for d in candidates)
    raise SystemExit(
        f"存在多个活跃任务，请加关键词或先设置激活：\n"
        f"  python3 ~/.claude/skills/control/scripts/set_active.py <关键词>\n\n"
        f"候选：\n  {names}"
    )


def find_control_doc(task_dir: Path) -> Path:
    main = find_main_doc(task_dir)
    if not main:
        raise SystemExit(f"未找到 {task_dir.name}/README.md")
    return main


def parse_subtasks(doc: Path) -> list[Subtask]:
    lines = doc.read_text(encoding="utf-8").splitlines()
    in_table = False
    header: dict[str, int] = {}
    tasks: list[Subtask] = []
    for raw in lines:
        line = raw.strip()
        if re.fullmatch(r"#+\s*(\d+\.\s*)?子任务总表", line):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if header:
                break
            continue
        if re.fullmatch(r"\|\s*-+\s*(\|\s*-+\s*)+\|?", line):
            continue
        cells = [c.strip().replace("`", "").strip() for c in line.strip("|").split("|")]
        if not header:
            for i, c in enumerate(cells):
                if c in {"编号", "序号"}: header["seq"] = i
                elif c in {"子任务", "任务名称", "子任务文件"}: header["name"] = i
                elif c in {"执行模式", "模式"}: header["mode"] = i
                elif c in {"状态", "当前状态"}: header["status"] = i
                elif c in {"依赖", "依赖关系"}: header["deps"] = i
                elif c in {"预期输出", "输出物", "做什么"}: header["output"] = i
            if not all(k in header for k in ["seq", "name", "status"]):
                raise SystemExit(f"子任务总表缺必要列: {cells}")
            continue
        def get(key: str, default: str = "") -> str:
            idx = header.get(key)
            return cells[idx] if idx is not None and idx < len(cells) else default
        tasks.append(Subtask(
            seq=get("seq"), name=get("name"),
            mode=get("mode", "（未标注）"),
            status=get("status"),
            deps=get("deps"),
            output=get("output"),
        ))
    return tasks


def pick_next(tasks: list[Subtask]) -> tuple[Subtask | None, str]:
    """选下一个可执行子任务。

    两级层次约束：
    - 永不推荐父任务（有子任务的 Tn）；只在叶子节点里挑
    - 依赖判定：依赖编号若是父 → 展开为所有直接子，全部已完成/已取消才算满足
    """
    all_seqs = [t.seq for t in tasks]
    seqs_set = set(all_seqs)
    completed_leaves = {
        t.seq for t in tasks
        if t.status in {"已完成", "已取消"} and not is_parent_seq(t.seq, seqs_set)
    }

    def deps_met(task: Subtask) -> tuple[bool, list[str]]:
        unmet: list[str] = []
        for dep in task.dep_list:
            for leaf in expand_dep_to_leaves(dep, all_seqs):
                if leaf not in completed_leaves:
                    unmet.append(leaf)
        return (not unmet), unmet

    leaves = [t for t in tasks if not is_parent_seq(t.seq, seqs_set)]

    in_progress = [t for t in leaves if t.status == "进行中"]
    if in_progress:
        return in_progress[0], "已有 进行中 子任务，优先恢复"

    pending = [t for t in leaves if t.status == "待完成"]
    for t in pending:
        ok, _ = deps_met(t)
        if ok:
            return t, "依赖均已满足"

    blocked = [t for t in leaves if t.status == "阻塞"]
    if not pending and not blocked:
        return None, "所有叶子子任务均已完成或取消，可考虑归档"

    reasons = []
    if blocked:
        reasons.append(f"阻塞子任务: {', '.join(t.seq for t in blocked)}")
    if pending:
        for t in pending:
            ok, unmet = deps_met(t)
            if not ok:
                reasons.append(f"{t.seq} 待: 依赖 {', '.join(unmet)} 未完成")
    return None, "无可推进子任务。" + "；".join(reasons)


def render(task_dir: Path, doc: Path, picked: Subtask | None, reason: str) -> str:
    out = [f"任务目录：`{task_dir.name}`", f"总控文档：`{doc.relative_to(PROJECT_ROOT)}`", ""]
    if picked is None:
        out.append(f"⚠ {reason}")
        return "\n".join(out)
    out.append(f"下一个可执行子任务：**{picked.seq}**（{reason}）")
    out.append("")
    out.append(f"- 名称：{picked.name}")
    out.append(f"- 当前状态：{picked.status}")
    out.append(f"- 依赖：{picked.deps or '无'}")
    out.append(f"- 预期输出：{picked.output}")
    out.append("")
    out.append("**执行边界**：只做这一个子任务，做完立刻停止。")
    out.append("执行前重读子任务详情中的「强制阅读」清单。")
    out.append("模型选择由你在新会话开头自行决定（用 `/model`）。")
    out.append("")
    out.append("---")
    out.append(render_session_prompt(task_dir, doc, picked))
    return "\n".join(out)


def render_session_prompt(task_dir: Path, doc: Path, picked: Subtask) -> str:
    """生成完整会话启动提示词，可直接复制到新会话。

    自动检测单文件 vs 拆分模式（看 task_dir 下是否有 T{seq}-*.md）。
    """
    doc_rel = doc.relative_to(PROJECT_ROOT)
    split_target = find_subtask_md(task_dir, picked.seq)
    if split_target:
        target_rel = split_target.relative_to(PROJECT_ROOT)
        body = (
            f"我要执行 {target_rel} 这个子任务（{picked.seq} - {picked.name}）。\n\n"
            f"请按以下步骤：\n"
            f"1. 读取 {target_rel}（本子任务工作包）\n"
            f"2. 读取该文件「强制阅读」列出的文件\n"
            f"3. 严格在本子任务范围内执行：做完「要做的事情」、产出「输出物」、通过「完成判定」、遵守「不做什么」\n"
            f"4. 完成后回填本文件的「当前状态」为已完成、「输出物」为实际产出文件\n"
            f"5. 同步更新 {task_dir.relative_to(PROJECT_ROOT)}/README.md 子任务总表对应行 + 进展记录\n"
            f"6. 不要做其他子任务，做完立刻停止并向我报告"
        )
    else:
        body = (
            f"我要执行 {doc_rel} 的 {picked.seq} 子任务（{picked.name}）。\n\n"
            f"请按以下步骤：\n"
            f"1. 读取这份总控的「任务背景」和子任务总表（不读其他子任务详情）\n"
            f"2. 读取本子任务详情：{picked.seq} - {picked.name}\n"
            f"3. 读取该子任务「强制阅读」列出的文件\n"
            f"4. 严格在 {picked.seq} 范围内执行：做完「要做的事情」、产出「输出物」、通过「完成判定」、遵守「不做什么」\n"
            f"5. 完成后回填总控对应字段：状态改为已完成、输出物填实际产出、追加进展记录一行\n"
            f"6. 不要做其他子任务，做完立刻停止并向我报告"
        )
    return (
        "**📋 会话启动提示词（复制下面这段到新会话）**：\n\n"
        "```\n"
        f"{body}\n"
        "```"
    )


def extract_subtask_section(doc: Path, seq: str) -> str:
    """从单文件主总控中抽取指定子任务详情段全文。

    匹配规则：起始行形如 `### {seq} ` 或 `### {seq}（中文标点）` 或纯 `### {seq}`，
    结束于下一个同级或上级标题（### 或 ##）。
    """
    lines = doc.read_text(encoding="utf-8").splitlines()
    start_pat = re.compile(rf"^###\s+{re.escape(seq)}([\s\S]|$)")
    out: list[str] = []
    in_section = False
    for line in lines:
        if not in_section:
            if start_pat.match(line):
                in_section = True
                out.append(line)
            continue
        if re.match(r"^###?\s+\S", line):
            break
        out.append(line)
    return "\n".join(out).rstrip()


def show_subtask(task_dir: Path, doc: Path, seq: str) -> str:
    """输出指定子任务的完整工作包内容（兼容单文件 / 拆分模式 + 两级层次）。"""
    split_target = find_subtask_md(task_dir, seq)
    if split_target:
        return f"# 子任务文件：{split_target.relative_to(PROJECT_ROOT)}\n\n{split_target.read_text(encoding='utf-8').rstrip()}"
    section = extract_subtask_section(doc, seq)
    if not section:
        return f"⚠ 未在 {doc.relative_to(PROJECT_ROOT)} 找到子任务 `{seq}` 的详情段。"
    header = f"# 子任务详情（来自 {doc.relative_to(PROJECT_ROOT)}）\n"
    return f"{header}\n{section}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword", nargs="?", help="任务关键词（不传按 active-control / 唯一兜底）")
    parser.add_argument("--show", metavar="Tn", help="输出指定子任务详情段全文（兼容单文件/拆分模式）")
    args = parser.parse_args()

    task_dir = find_task_dir(args.keyword)
    doc = find_control_doc(task_dir)

    if args.show:
        print(show_subtask(task_dir, doc, args.show))
        return 0

    tasks = parse_subtasks(doc)
    picked, reason = pick_next(tasks)
    print(render(task_dir, doc, picked, reason))
    return 0 if picked else 2


if __name__ == "__main__":
    sys.exit(main())
