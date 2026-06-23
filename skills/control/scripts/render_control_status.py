#!/usr/bin/env python3
"""
渲染指定总控的状态表（只读）。

任务目录通过扫描 docs/00-任务总控/ 下含 README.md 的子目录获得。
多激活时通过 .claude/local/active-control 显式指定（每个 worktree 独立）。
worktree 真值用 `git worktree list`，本脚本不再镜像它。

输出契约（与 control/SKILL.md 「/control status 输出契约」绑定）：
- status 模式输出固定 markdown 结构：`# 总控状态` 块头 + `## 子任务总表` + 五列表
  （编号 / 子任务 / 状态 / 依赖 / 预期输出）
- 总体状态从子任务表派生，优先级：阻塞 > 进行中 > 未启动 > 已完成
- 顶部 `> 当前状态：` 行（如存在）仅作"附注"展示，不参与派生
- `--list` 模式输出 `# 活跃总控` + 单列表
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    PROJECT_ROOT,
    CONTROL_ROOT,
    STATUS_ENUM,
    PARENT_STATUS_PLACEHOLDER,
    list_active_task_dirs,
    find_main_doc,
    read_active_control,
    is_parent_seq,
    direct_children,
    derive_status_from_counts,
)


@dataclass
class ActiveTask:
    task_dir: str


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def parse_markdown_table(lines: Iterable[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    in_table = False
    for raw in lines:
        line = raw.strip()
        if not in_table and not line.startswith("|"):
            continue
        if not line.startswith("|"):
            break
        in_table = True
        if re.fullmatch(r"\|\s*-+\s*(\|\s*-+\s*)+\|?", line):
            continue
        cells = [c.strip().replace("`", "").strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    return rows


def read_active_tasks() -> list[ActiveTask]:
    return [ActiveTask(task_dir=d.name) for d in list_active_task_dirs()]


def list_active_tasks(tasks: list[ActiveTask]) -> str:
    header = "| 任务目录 |\n| --- |"
    body = [f"| `{t.task_dir}` |" for t in tasks]
    return "\n".join(["# 活跃总控", "", header, *body])


def choose_task(tasks: list[ActiveTask], keyword: str | None) -> ActiveTask | None:
    """优先级：keyword > active-control 文件 > 唯一兜底。"""
    if keyword:
        key = normalize(keyword)
        matched = [t for t in tasks if key in normalize(t.task_dir)]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            print("匹配到多份总控，请补更具体关键词：\n")
            print(list_active_tasks(matched))
            return None
        print(f"未匹配关键词 '{keyword}' 的总控。")
        return None

    active = read_active_control()
    if active:
        bound = [t for t in tasks if t.task_dir == active]
        if bound:
            return bound[0]
        print(
            f"⚠ active-control 文件指向 '{active}'，但未找到匹配的活跃任务（可能已归档或重命名）。\n"
            f"  请检查 .claude/local/active-control 或运行 set_active.py --clear 清除。\n",
            file=sys.stderr,
        )

    if len(tasks) == 1:
        return tasks[0]

    print(
        "存在多份活跃总控。请加关键词，或先设置激活：\n"
        "  python3 ~/.claude/skills/control/scripts/set_active.py <关键词>\n"
    )
    print(list_active_tasks(tasks))
    return None


def find_control_doc(task: ActiveTask) -> Path:
    task_dir = CONTROL_ROOT / task.task_dir
    main = find_main_doc(task_dir)
    if not main:
        raise FileNotFoundError(f"未找到主总控文档（README.md）: {task_dir}")
    return main


def extract_current_status(doc_lines: list[str]) -> str | None:
    """读总控顶部 `> 当前状态：` 行（可能不存在）。仅作附注。"""
    for line in doc_lines:
        if line.startswith("> 当前状态："):
            return line.removeprefix("> 当前状态：").strip()
    return None


def format_counts(status_counts: dict[str, int]) -> str:
    parts = []
    for st in STATUS_ENUM:
        n = status_counts.get(st, 0)
        if n > 0:
            parts.append(f"{st} {n}")
    return "、".join(parts) if parts else "空"


def extract_subtask_table(doc_lines: list[str]) -> list[list[str]]:
    for idx, line in enumerate(doc_lines):
        if re.fullmatch(r"#+\s*(\d+\.\s*)?子任务总表", line.strip()):
            start = idx + 1
            while start < len(doc_lines) and not doc_lines[start].strip().startswith("|"):
                start += 1
            table_rows = parse_markdown_table(doc_lines[start:])
            if table_rows:
                return table_rows
    raise ValueError("未找到\"子任务总表\"表格")


def find_column(header: list[str], names: set[str]) -> int | None:
    normalized = {normalize(name) for name in names}
    for idx, cell in enumerate(header):
        if normalize(cell) in normalized:
            return idx
    return None


def read_cell(row: list[str], idx: int | None, default: str = "") -> str:
    if idx is None or idx >= len(row):
        return default
    return row[idx]


def render_status_table(doc_path: Path) -> str:
    doc_lines = doc_path.read_text(encoding="utf-8").splitlines()
    annotated_status = extract_current_status(doc_lines)
    rows = extract_subtask_table(doc_lines)
    header = rows[0]
    seq_idx = find_column(header, {"编号", "序号"})
    name_idx = find_column(header, {"子任务", "任务名称", "子任务文件"})
    status_idx = find_column(header, {"状态", "当前状态"})
    deps_idx = find_column(header, {"依赖", "依赖关系"})
    summary_idx = find_column(header, {"预期输出", "输出物", "做什么"})
    granularity_idx = find_column(header, {"当前粒度", "粒度"})
    required = {
        "编号": seq_idx,
        "子任务": name_idx,
        "状态": status_idx,
        "预期输出": summary_idx,
    }
    missing = [name for name, idx in required.items() if idx is None]
    if missing:
        raise ValueError(f"子任务总表缺少必要列 {missing}: {header}")

    data_rows = rows[1:]
    all_seqs = [read_cell(row, seq_idx).strip() for row in data_rows]

    # 派生父行状态：父行原始状态列应为 "派生" 占位，从子任务聚合
    # 统计/派生只数叶子节点（父不计入计数）
    leaf_status_counts: dict[str, int] = {}
    parent_derived: dict[str, str] = {}
    for row, seq in zip(data_rows, all_seqs):
        if is_parent_seq(seq, set(all_seqs)):
            child_seqs = direct_children(seq, all_seqs)
            child_counts: dict[str, int] = {}
            for s in child_seqs:
                idx = all_seqs.index(s)
                cst = read_cell(data_rows[idx], status_idx).strip()
                if cst:
                    child_counts[cst] = child_counts.get(cst, 0) + 1
            parent_derived[seq] = derive_status_from_counts(child_counts)
        else:
            st = read_cell(row, status_idx).strip()
            if st:
                leaf_status_counts[st] = leaf_status_counts.get(st, 0) + 1

    overall = derive_status_from_counts(leaf_status_counts)
    counts_line = format_counts(leaf_status_counts)
    total = sum(leaf_status_counts.values())
    task_dir_name = doc_path.parent.name

    has_parents = bool(parent_derived)
    output_lines = [
        "# 总控状态",
        "",
        f"- 任务目录：`{task_dir_name}`",
        f"- 主总控：`{doc_path.relative_to(PROJECT_ROOT)}`",
        f"- 总体状态（派生）：{overall}",
        f"- 叶子任务统计：共 {total} 个叶子（{counts_line}）",
    ]
    if has_parents:
        parents_line = "、".join(f"{p}→{s}" for p, s in parent_derived.items())
        output_lines.append(f"- 父任务派生状态：{parents_line}")
    if annotated_status:
        output_lines.append(f"- 顶部附注（`> 当前状态：` 行，仅供参考）：{annotated_status}")
    output_lines.extend([
        "",
        "## 子任务总表",
        "",
        "| 编号 | 子任务 | 状态 | 依赖 | 预期输出 |",
        "| --- | --- | --- | --- | --- |",
    ])
    for row, seq in zip(data_rows, all_seqs):
        name = read_cell(row, name_idx)
        if seq in parent_derived:
            status = f"{parent_derived[seq]}（派生）"
        else:
            status = read_cell(row, status_idx)
        deps = read_cell(row, deps_idx, "未列")
        if deps_idx is None and granularity_idx is not None:
            deps = f"未列（粒度：{read_cell(row, granularity_idx)}）"
        summary = read_cell(row, summary_idx)
        output_lines.append(f"| `{seq}` | {name} | {status} | {deps} | {summary} |")
    return "\n".join(output_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染当前总控状态表（只读）")
    parser.add_argument("keyword", nargs="?", help="任务关键词")
    parser.add_argument("--list", action="store_true", help="只列出当前活跃总控")
    args = parser.parse_args()

    tasks = read_active_tasks()
    if not tasks:
        print(f"未发现活跃总控（{CONTROL_ROOT.relative_to(PROJECT_ROOT)} 下没有含 README.md 的子目录）。")
        print("提示：先运行 bootstrap_project.py 初始化骨架，再用 task-control-doc skill 创建任务。")
        return 1

    if args.list:
        print(list_active_tasks(tasks))
        return 0

    task = choose_task(tasks, args.keyword)
    if not task:
        return 2

    doc_path = find_control_doc(task)
    print(render_status_table(doc_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
