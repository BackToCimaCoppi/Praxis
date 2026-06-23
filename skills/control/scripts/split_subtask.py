#!/usr/bin/env python3
"""
把一个一级父任务 Tn 拆分为 Tn.1 ~ Tn.N 子任务（仅支持两级；不能拆 Tn.x）。

用法：
    split_subtask.py <keyword> <Tn> --subtasks "Tn.1=名1,Tn.2=名2,..."
                                    [--reason "拆分理由"]
                                    [--apply]   # 默认 dry-run

行为（按总控当前布局自适应）：
- 单文件模式（仅 README.md，无 Tk-*.md / Tk/Tk.md）：
    * 子任务总表：Tn 行状态改 `派生`；Tn 下方插入 N 行 Tn.x（状态 `待完成`）
    * 子任务详情：保留 ### Tn 段，末尾追加「已拆分清单」；
      在该段后追加 N 个 ### Tn.x 骨架段
- 拆分模式（存在 Tk-*.md 或 Tk/Tk.md）：
    * 子任务总表：同上
    * 文件迁移：若存在 Tn-*.md → 移到 <task_dir>/Tn/Tn.md；并追加「已拆分清单」
      若不存在 → 创建 <task_dir>/Tn/Tn.md 占位
    * 在 <task_dir>/Tn/ 下生成 N 个 Tn.x-{名}.md 子任务工作包骨架
- 在 README 的「进展记录」段追加一行变更说明

约束（任一违反则拒绝）：
- Tn 必须存在于子任务总表
- Tn 当前状态不能是 `已完成` / `已取消`
- Tn 不能是子任务（含 `.`），不允许深层拆分
- Tn 不能已经被拆过（不存在 Tn.x 行）
- --subtasks 至少 2 个，每个编号必须形如 Tn.{m} 且 m 从 1 起递增
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    PROJECT_ROOT,
    CONTROL_ROOT,
    list_active_task_dirs,
    find_main_doc,
    is_parent_seq,
    is_child_seq,
)


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------

@dataclass
class ChildSpec:
    seq: str
    name: str


def parse_subtasks_arg(parent_seq: str, raw: str) -> list[ChildSpec]:
    items = [seg.strip() for seg in raw.split(",") if seg.strip()]
    if len(items) < 2:
        raise SystemExit("--subtasks 至少要给 2 个子任务，否则没必要拆")
    parsed: list[ChildSpec] = []
    expected_prefix = parent_seq + "."
    for i, item in enumerate(items, start=1):
        if "=" not in item:
            raise SystemExit(f"--subtasks 段格式错误（应为 `Tn.m=名称`）：{item}")
        seq, name = (s.strip() for s in item.split("=", 1))
        if not seq.startswith(expected_prefix):
            raise SystemExit(f"子任务编号 {seq} 不属于 {parent_seq} 的子（应以 {expected_prefix} 开头）")
        suffix = seq[len(expected_prefix):]
        if not suffix.isdigit() or int(suffix) != i:
            raise SystemExit(f"子任务编号 {seq} 必须从 {parent_seq}.1 开始按序递增，第 {i} 个应为 {parent_seq}.{i}")
        if not name:
            raise SystemExit(f"子任务 {seq} 缺少名称")
        if "." in suffix:
            raise SystemExit(f"不允许深层拆分（{seq}）")
        parsed.append(ChildSpec(seq=seq, name=name))
    return parsed


# ---------------------------------------------------------------------------
# 任务目录定位 + 文档解析
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def find_task_dir(keyword: str) -> Path:
    key = _normalize(keyword)
    candidates = [d for d in list_active_task_dirs() if key in _normalize(d.name)]
    if not candidates:
        raise SystemExit(f"未找到匹配关键词 '{keyword}' 的活跃任务目录")
    if len(candidates) > 1:
        names = "\n  ".join(d.name for d in candidates)
        raise SystemExit(f"匹配多个任务目录，请补关键词：\n  {names}")
    return candidates[0]


def detect_mode(task_dir: Path) -> str:
    """检测当前总控是 split 还是 single。"""
    has_split = any(task_dir.glob("T*-*.md")) or any(
        d.is_dir() and (d / f"{d.name}.md").exists()
        for d in task_dir.iterdir() if d.name.startswith("T")
    )
    return "split" if has_split else "single"


# ---------------------------------------------------------------------------
# 子任务总表读写
# ---------------------------------------------------------------------------

TABLE_HEADER_PAT = re.compile(r"#+\s*(\d+\.\s*)?子任务总表")
TABLE_SEPARATOR_PAT = re.compile(r"\|\s*-+\s*(\|\s*-+\s*)+\|?")


@dataclass
class SubtaskRow:
    seq: str
    raw: str            # 原始行（不含尾部换行）
    line_index: int     # 在 doc_lines 中的行号
    cells: list[str]    # 解析后的单元格


@dataclass
class TableInfo:
    header_index: int       # 表头行的 line_index
    header_cells: list[str]
    seq_col: int
    status_col: int
    name_col: int
    deps_col: int | None
    output_col: int | None
    rows: list[SubtaskRow]  # 数据行（按出现顺序）
    table_end: int          # 表格之后第一行非 | 开头的 line_index（用于插入新行的边界）


def parse_table(doc_lines: list[str]) -> TableInfo:
    in_table = False
    header_idx: int | None = None
    header_cells: list[str] = []
    seq_col = status_col = name_col = -1
    deps_col: int | None = None
    output_col: int | None = None
    rows: list[SubtaskRow] = []
    table_end = len(doc_lines)
    for i, raw in enumerate(doc_lines):
        line = raw.strip()
        if not in_table:
            if TABLE_HEADER_PAT.fullmatch(line):
                in_table = True
            continue
        if not line.startswith("|"):
            if header_idx is not None:
                table_end = i
                break
            continue
        if TABLE_SEPARATOR_PAT.fullmatch(line):
            continue
        cells = [c.strip().replace("`", "").strip() for c in line.strip("|").split("|")]
        if header_idx is None:
            header_idx = i
            header_cells = cells
            for j, c in enumerate(cells):
                if c in {"编号", "序号"}: seq_col = j
                elif c in {"子任务", "任务名称", "子任务文件"}: name_col = j
                elif c in {"状态", "当前状态"}: status_col = j
                elif c in {"依赖", "依赖关系"}: deps_col = j
                elif c in {"预期输出", "输出物", "做什么"}: output_col = j
            if seq_col < 0 or status_col < 0 or name_col < 0:
                raise SystemExit(f"子任务总表缺少必要列: {cells}")
            continue
        rows.append(SubtaskRow(seq=cells[seq_col] if seq_col < len(cells) else "?",
                                raw=raw, line_index=i, cells=cells))
    if header_idx is None:
        raise SystemExit("未找到子任务总表")
    return TableInfo(header_index=header_idx, header_cells=header_cells,
                      seq_col=seq_col, status_col=status_col, name_col=name_col,
                      deps_col=deps_col, output_col=output_col,
                      rows=rows, table_end=table_end)


def make_row(table: TableInfo, seq: str, name: str, status: str,
              deps: str = "无", output: str = "") -> str:
    n = len(table.header_cells)
    cells = ["" for _ in range(n)]
    cells[table.seq_col] = seq
    cells[table.name_col] = name
    cells[table.status_col] = status
    if table.deps_col is not None:
        cells[table.deps_col] = deps
    if table.output_col is not None:
        cells[table.output_col] = output
    return "| " + " | ".join(cells) + " |"


# ---------------------------------------------------------------------------
# 单文件模式下：子任务详情段操作
# ---------------------------------------------------------------------------

SECTION_HEAD_PAT = re.compile(r"^###\s+(T\S+)")


def find_subtask_section(doc_lines: list[str], seq: str) -> tuple[int, int] | None:
    """返回 (start_index, end_index_exclusive) 表示 `### {seq}` 段范围。
    end 是下一个 ###/##/# 标题行的 index，或文件末尾。
    """
    start = None
    for i, line in enumerate(doc_lines):
        m = SECTION_HEAD_PAT.match(line)
        if m and m.group(1) == seq:
            start = i
            break
    if start is None:
        return None
    end = len(doc_lines)
    for i in range(start + 1, len(doc_lines)):
        if re.match(r"^#{1,3}\s+\S", doc_lines[i]):
            end = i
            break
    return start, end


def child_section_skeleton(parent_seq: str, child: ChildSpec, parent_name: str) -> list[str]:
    return [
        f"### {child.seq} {child.name}",
        "",
        "- **当前状态**：待完成",
        "",
        f"> 由 `split_subtask.py` 自动生成；父任务：{parent_seq} {parent_name}。请补全下列字段。",
        "",
        "#### 子任务背景",
        "",
        "（用一段话讲清楚为什么从父任务里单独拆出这件事）",
        "",
        "#### 强制阅读（精准 1-3 个）",
        "",
        "- `路径`：为什么必须读",
        "",
        "#### 输入",
        "",
        "（前置依赖的产出物）",
        "",
        "#### 要做的事情",
        "",
        "- 第一步",
        "- 第二步",
        "",
        "#### 不做什么（可选）",
        "",
        "- ",
        "",
        "#### 预期效果",
        "",
        "（执行完后系统/文档应该是什么状态）",
        "",
        "#### 输出物",
        "",
        "- `具体路径/文件名`：内容简述",
        "",
        "#### 完成判定",
        "",
        "- [ ] 输出物已产出",
        "",
        "#### 依赖关系",
        "",
        "- 依赖：（前一个子任务编号或「无」）",
        "- 阻塞：（下一个子任务编号或「无」）",
        "",
        "#### 风险与注意事项",
        "",
        "- ",
        "",
        "---",
        "",
    ]


def child_file_skeleton(parent_seq: str, parent_name: str, child: ChildSpec, task_dir_name: str) -> str:
    rel_path = f"docs/00-任务总控/{task_dir_name}/{parent_seq}/{child.seq}-{child.name}.md"
    return "\n".join([
        f"# {child.seq} {child.name}",
        "",
        f"> 父任务：{parent_seq} {parent_name}（详见 `{parent_seq}.md`）",
        "",
        "- **当前状态**：待完成",
        "",
        "## 子任务背景",
        "",
        "（用一段话讲清楚为什么从父任务里单独拆出这件事）",
        "",
        "## 强制阅读（精准 1-3 个）",
        "",
        "- `路径`：为什么必须读",
        "",
        "## 输入",
        "",
        "（前置依赖的产出物）",
        "",
        "## 要做的事情",
        "",
        "- 第一步",
        "- 第二步",
        "",
        "## 不做什么（可选）",
        "",
        "- ",
        "",
        "## 预期效果",
        "",
        "## 输出物",
        "",
        "- `具体路径/文件名`：内容简述",
        "",
        "## 完成判定",
        "",
        "- [ ] 输出物已产出",
        "",
        "## 依赖关系",
        "",
        "- 依赖：（前一个子任务编号或「无」）",
        "- 阻塞：（下一个子任务编号或「无」）",
        "",
        "## 风险与注意事项",
        "",
        "- ",
        "",
        "## 会话启动提示词",
        "",
        "```",
        f"我要执行 {rel_path} 这个子任务（{child.seq} - {child.name}）。",
        "",
        "请按以下步骤：",
        "1. 读取本文件（含强制阅读、输入、要做的事情、不做什么、输出物、完成判定）",
        "2. 读取「强制阅读」列出的文件",
        "3. 严格在本子任务范围内执行",
        "4. 完成后回填本文件的「当前状态」为已完成、「输出物」为实际产出文件",
        f"5. 同步更新 docs/00-任务总控/{task_dir_name}/README.md 子任务总表对应行 + 进展记录",
        "6. 不要做其他子任务，做完立刻停止并向我报告",
        "```",
        "",
    ])


def split_clause_for_parent(parent_seq: str, children: list[ChildSpec]) -> list[str]:
    lines = [
        "",
        f"> **已拆分（{_dt.date.today().isoformat()}）**：本任务已拆为以下子任务，本段仅保留背景/范围作为父任务说明，具体施工见各子任务。",
        "",
    ]
    for c in children:
        lines.append(f"> - `{c.seq}`：{c.name}")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# 进展记录追加
# ---------------------------------------------------------------------------

PROGRESS_PAT = re.compile(r"#+\s*(\d+\.\s*)?进展记录")


def insert_progress_line(doc_lines: list[str], line: str) -> list[str]:
    """在「进展记录」段下追加一行；若没有该段，追加到文末。"""
    for i, raw in enumerate(doc_lines):
        if PROGRESS_PAT.fullmatch(raw.strip()):
            j = i + 1
            while j < len(doc_lines) and not doc_lines[j].strip():
                j += 1
            return doc_lines[:j] + [line] + doc_lines[j:]
    return doc_lines + ["", "## 进展记录", "", line]


# ---------------------------------------------------------------------------
# 计划/执行
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    task_dir: Path
    doc_path: Path
    mode: str
    parent_seq: str
    parent_name: str
    children: list[ChildSpec]
    reason: str
    # 计划内容
    new_doc_lines: list[str]
    file_ops: list[tuple[str, Path, Path | str | None]] = field(default_factory=list)
    # file_ops: (op, target_path, payload) ; op in {"mkdir", "move", "write_new"}


def build_plan(task_dir: Path, parent_seq: str, children: list[ChildSpec], reason: str) -> Plan:
    doc_path = find_main_doc(task_dir)
    if not doc_path:
        raise SystemExit(f"未找到 {task_dir.name}/README.md")
    doc_lines = doc_path.read_text(encoding="utf-8").splitlines()

    table = parse_table(doc_lines)
    parent_row = next((r for r in table.rows if r.seq == parent_seq), None)
    if not parent_row:
        raise SystemExit(f"子任务总表中未找到 {parent_seq}")
    parent_status = parent_row.cells[table.status_col] if table.status_col < len(parent_row.cells) else ""
    if parent_status in {"已完成", "已取消"}:
        raise SystemExit(f"{parent_seq} 状态为「{parent_status}」，不允许拆分")
    if is_child_seq(parent_seq):
        raise SystemExit(f"{parent_seq} 已是子任务，不允许深层拆分")
    all_seqs = {r.seq for r in table.rows}
    if is_parent_seq(parent_seq, all_seqs):
        raise SystemExit(f"{parent_seq} 已被拆过，不允许再次拆")
    for c in children:
        if c.seq in all_seqs:
            raise SystemExit(f"子任务编号 {c.seq} 已存在")

    raw_name_cell = parent_row.cells[table.name_col] if table.name_col < len(parent_row.cells) else parent_seq
    # 清理 markdown 链接：[text](url) → text
    parent_name = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw_name_cell).strip()
    # 进一步剥掉文件名前缀（如 `T2-大任务.md` → `大任务`）
    m = re.match(rf"^{re.escape(parent_seq)}[-_\s]*(.+?)(?:\.md)?$", parent_name)
    if m:
        parent_name = m.group(1).strip()
    parent_deps = parent_row.cells[table.deps_col] if table.deps_col is not None and table.deps_col < len(parent_row.cells) else "无"
    parent_output = parent_row.cells[table.output_col] if table.output_col is not None and table.output_col < len(parent_row.cells) else ""

    # 1. 改子任务总表：父行状态改派生 + 在父行后插入子行
    new_lines = list(doc_lines)
    # 改父行
    new_parent_cells = list(parent_row.cells)
    while len(new_parent_cells) < len(table.header_cells):
        new_parent_cells.append("")
    new_parent_cells[table.status_col] = "派生"
    mode = detect_mode(task_dir)  # 提前判定，下方还要用
    # 若「子任务文件」列原本是 markdown 链接（拆分模式总控），更新指向新父文件 Tn/Tn.md
    if mode == "split" and "[" in raw_name_cell and "](" in raw_name_cell:
        new_parent_cells[table.name_col] = f"[`{parent_seq}/{parent_seq}.md`]({parent_seq}/{parent_seq}.md)"
    new_lines[parent_row.line_index] = "| " + " | ".join(new_parent_cells) + " |"

    child_rows_md: list[str] = []
    for i, c in enumerate(children):
        prev_dep = "无" if i == 0 else children[i-1].seq
        if mode == "split":
            name_cell = f"[`{c.seq}-{c.name}.md`]({parent_seq}/{c.seq}-{c.name}.md)"
        else:
            name_cell = c.name
        child_rows_md.append(make_row(
            table, c.seq, name_cell, "待完成",
            deps=prev_dep,
            output="(待填)",
        ))
    # 插入位置：父行下一行（line_index + 1）
    insert_at = parent_row.line_index + 1
    new_lines = new_lines[:insert_at] + child_rows_md + new_lines[insert_at:]

    # 2. 子任务详情 / 文件
    file_ops: list[tuple[str, Path, Path | str | None]] = []
    if mode == "single":
        # 拆 ### 父段
        section = find_subtask_section(new_lines, parent_seq)
        if section:
            sec_start, sec_end = section
            # 把 clause 插在父段实质内容尾部（跳过结尾的空行 / `---` 分隔线）
            clause_insert = sec_end
            while clause_insert - 1 > sec_start and (
                not new_lines[clause_insert - 1].strip()
                or new_lines[clause_insert - 1].strip() == "---"
            ):
                clause_insert -= 1
            clause = split_clause_for_parent(parent_seq, children)
            new_lines = new_lines[:clause_insert] + clause + new_lines[clause_insert:]
            # 子段（含各自 `---`）紧跟在父段整体之后，即 sec_end 之后（已被 clause 推后）
            child_sections: list[str] = []
            for c in children:
                child_sections.extend(child_section_skeleton(parent_seq, c, parent_name))
            insert_pos = sec_end + len(clause)
            new_lines = new_lines[:insert_pos] + child_sections + new_lines[insert_pos:]
        # 单文件模式不创建额外文件
    else:
        # 拆分模式：建 Tn/Tn.md + Tn/Tn.x-名.md
        parent_dir = task_dir / parent_seq
        parent_doc = parent_dir / f"{parent_seq}.md"
        file_ops.append(("mkdir", parent_dir, None))
        existing = list(task_dir.glob(f"{parent_seq}-*.md"))
        if len(existing) == 1:
            file_ops.append(("move", existing[0], parent_doc))
        elif len(existing) > 1:
            raise SystemExit(f"发现多个 {parent_seq}-*.md，无法判定主文件：{[p.name for p in existing]}")
        else:
            # 没有原 Tn-*.md（少见，比如总控刚建好就拆），创建一个占位
            placeholder = "\n".join([
                f"# {parent_seq} {parent_name}（父任务）",
                "",
                "> 由 `split_subtask.py` 自动创建占位。本任务已被拆分，本文件仅保留背景/范围。",
                "",
                "## 子任务背景",
                "",
                "（请补全）",
                "",
            ])
            file_ops.append(("write_new", parent_doc, placeholder))
        # 在 Tn.md 末尾追加 split clause（应用阶段才追加，写入时拼接 in apply）
        # 这里只登记意图：用特殊 op
        clause_text = "\n".join(split_clause_for_parent(parent_seq, children))
        file_ops.append(("append_to_parent_doc", parent_doc, clause_text))
        # N 个子任务文件
        for c in children:
            child_file = parent_dir / f"{c.seq}-{c.name}.md"
            content = child_file_skeleton(parent_seq, parent_name, c, task_dir.name)
            file_ops.append(("write_new", child_file, content))

    # 3. 进展记录追加
    progress_line = (
        f"- {_dt.date.today().isoformat()}：`{parent_seq}` 拆分为 "
        f"{', '.join(f'`{c.seq}`' for c in children)}（理由：{reason}）"
    )
    new_lines = insert_progress_line(new_lines, progress_line)

    return Plan(
        task_dir=task_dir,
        doc_path=doc_path,
        mode=mode,
        parent_seq=parent_seq,
        parent_name=parent_name,
        children=children,
        reason=reason,
        new_doc_lines=new_lines,
        file_ops=file_ops,
    )


def print_plan(plan: Plan, apply: bool) -> None:
    mode_tag = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode_tag}] 拆分计划：{plan.parent_seq}（{plan.parent_name}）→ "
          f"{', '.join(c.seq for c in plan.children)}")
    print(f"  当前布局：{plan.mode}")
    print(f"  理由：{plan.reason}")
    print(f"  README.md 改动：")
    print(f"    - 子任务总表 {plan.parent_seq} 状态列 → `派生`")
    print(f"    - 在 {plan.parent_seq} 行下方插入 {len(plan.children)} 行子任务")
    if plan.mode == "single":
        print(f"    - ### {plan.parent_seq} 段末尾追加「已拆分清单」")
        print(f"    - 在 {plan.parent_seq} 段之后插入 {len(plan.children)} 个 ### 子任务详情骨架")
    print(f"    - 进展记录追加一行")
    if plan.mode == "split":
        print(f"  文件改动：")
        for op, path, payload in plan.file_ops:
            rel = path.relative_to(PROJECT_ROOT) if path.is_absolute() else path
            if op == "mkdir":
                print(f"    - mkdir {rel}")
            elif op == "move":
                target = payload.relative_to(PROJECT_ROOT) if isinstance(payload, Path) else payload
                print(f"    - move {rel} → {target}")
            elif op == "write_new":
                print(f"    - write_new {rel}")
            elif op == "append_to_parent_doc":
                print(f"    - append 已拆分清单 → {rel}")


def apply_plan(plan: Plan) -> None:
    # 1. 写 README（先记录在内存里）
    new_text = "\n".join(plan.new_doc_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    # 2. 文件操作（保证幂等：mkdir 安全；move 在 apply 前校验目标不存在）
    pending_append: list[tuple[Path, str]] = []
    for op, path, payload in plan.file_ops:
        if op == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
        elif op == "move":
            target = payload  # type: ignore
            if not isinstance(target, Path):
                raise SystemExit(f"move op payload 必须是 Path: {target}")
            if target.exists():
                raise SystemExit(f"move 目标已存在：{target}")
            shutil.move(str(path), str(target))
        elif op == "write_new":
            if path.exists():
                raise SystemExit(f"write_new 目标已存在：{path}")
            path.write_text(payload, encoding="utf-8")  # type: ignore
        elif op == "append_to_parent_doc":
            pending_append.append((path, payload))  # type: ignore
        else:
            raise SystemExit(f"未知 file_op：{op}")
    for path, clause_text in pending_append:
        if not path.exists():
            raise SystemExit(f"父任务文件不存在，无法追加：{path}")
        existing = path.read_text(encoding="utf-8").rstrip()
        path.write_text(existing + "\n\n" + clause_text + "\n", encoding="utf-8")
    # 3. 最后写 README（避免文件操作出错前已改）
    plan.doc_path.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("keyword", help="任务关键词")
    parser.add_argument("parent_seq", help="要拆分的父任务编号，如 T3")
    parser.add_argument("--subtasks", required=True,
                        help='子任务清单，格式 "Tn.1=名1,Tn.2=名2,..."')
    parser.add_argument("--reason", default="拆分以减小工作包粒度",
                        help="拆分理由（写入进展记录）")
    parser.add_argument("--apply", action="store_true", help="真正执行（默认 dry-run）")
    args = parser.parse_args()

    task_dir = find_task_dir(args.keyword)
    # 先做一轮早期校验（让报错更精确）：父是否存在、是否已被拆
    doc_path = find_main_doc(task_dir)
    if doc_path:
        early_table = parse_table(doc_path.read_text(encoding="utf-8").splitlines())
        early_seqs = {r.seq for r in early_table.rows}
        if args.parent_seq not in early_seqs:
            raise SystemExit(f"子任务总表中未找到 {args.parent_seq}")
        if is_parent_seq(args.parent_seq, early_seqs):
            existing = sorted(s for s in early_seqs if s.startswith(args.parent_seq + "."))
            raise SystemExit(
                f"{args.parent_seq} 已被拆过（现有子任务：{', '.join(existing)}），"
                f"不允许再次拆。若要继续追加子任务请手动编辑总表。"
            )
        if is_child_seq(args.parent_seq):
            raise SystemExit(f"{args.parent_seq} 已是子任务，不允许深层拆分")
    children = parse_subtasks_arg(args.parent_seq, args.subtasks)
    plan = build_plan(task_dir, args.parent_seq, children, args.reason)
    print_plan(plan, args.apply)

    if not args.apply:
        print("\n（dry-run，未写入。加 --apply 才真正执行。）")
        return 0

    apply_plan(plan)
    print("\n拆分完成。下一步：")
    print(f"  1. 编辑各子任务骨架（README.md 中的 ### {plan.parent_seq}.x 段 或 "
          f"{plan.parent_seq}/{plan.parent_seq}.x-*.md），补全强制阅读、输入、要做的事情、输出物等字段")
    print(f"  2. 运行 render_control_status.py 确认派生状态正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
