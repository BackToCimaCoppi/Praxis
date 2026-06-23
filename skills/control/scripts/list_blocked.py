#!/usr/bin/env python3
"""
扫描所有活跃总控，列出处于 阻塞 状态的子任务。

输出表格：任务目录 / 子任务编号 / 子任务名称 / 阻塞原因摘要。
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import list_active_task_dirs, find_main_doc


@dataclass
class BlockedItem:
    task_dir: str
    seq: str
    name: str
    mode: str
    reason: str


def parse_subtasks(doc: Path) -> list[BlockedItem]:
    lines = doc.read_text(encoding="utf-8").splitlines()
    in_table = False
    header: dict[str, int] = {}
    blocked: list[BlockedItem] = []

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
            continue
        if "status" not in header or header["status"] >= len(cells):
            continue
        if cells[header["status"]] != "阻塞":
            continue
        seq = cells[header["seq"]] if header.get("seq") is not None and header["seq"] < len(cells) else "?"
        name = cells[header["name"]] if header.get("name") is not None and header["name"] < len(cells) else ""
        mode = cells[header["mode"]] if header.get("mode") is not None and header["mode"] < len(cells) else ""
        reason = extract_block_reason(lines, seq)
        blocked.append(BlockedItem(
            task_dir=doc.parent.name, seq=seq, name=name, mode=mode, reason=reason,
        ))
    return blocked


def extract_block_reason(lines: list[str], seq: str) -> str:
    """在子任务详情段落里找「风险与注意事项」或显式 阻塞原因 字段。"""
    pattern = re.compile(rf"^#+\s*{re.escape(seq)}\s")
    in_section = False
    section_lines: list[str] = []
    for line in lines:
        if pattern.match(line.strip()):
            in_section = True
            continue
        if in_section:
            if re.match(r"^#+\s+\S", line) and not pattern.match(line.strip()):
                break
            section_lines.append(line)

    for line in section_lines:
        s = line.strip().lstrip("-").strip()
        if s.startswith(("阻塞原因", "阻塞:", "阻塞：")):
            return s.split("：", 1)[-1].split(":", 1)[-1].strip()[:80]
    for line in section_lines:
        if "阻塞" in line:
            return line.strip().lstrip("-").strip()[:80]
    return "（未在子任务详情找到阻塞说明）"


def scan() -> list[BlockedItem]:
    items: list[BlockedItem] = []
    for d in list_active_task_dirs():
        doc = find_main_doc(d)
        if doc is None:
            continue
        items.extend(parse_subtasks(doc))
        # 拆分模式：子任务详情在 T{n}-...md 文件里，单独扫
        for sub in sorted(d.glob("T*-*.md")):
            items.extend(parse_subtasks(sub))
    return items


def render(items: list[BlockedItem]) -> str:
    if not items:
        return "未发现阻塞子任务。"
    out = ["| 任务目录 | 编号 | 名称 | 阻塞原因 |", "| --- | --- | --- | --- |"]
    seen = set()
    for it in items:
        key = (it.task_dir, it.seq)
        if key in seen:
            continue
        seen.add(key)
        reason = it.reason.replace("|", "\\|")
        out.append(f"| `{it.task_dir}` | `{it.seq}` | {it.name} | {reason} |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    items = scan()
    print(render(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
