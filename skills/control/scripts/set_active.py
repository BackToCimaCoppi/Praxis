#!/usr/bin/env python3
"""
管理当前 worktree 的激活总控配置。

文件位置：`<PROJECT_ROOT>/.claude/local/active-control`（不进版本控制，每个 worktree 物理隔离）

用法：
  set_active.py <关键词>      # 校验匹配后写入文件（保存任务目录精确名）
  set_active.py --clear      # 清除激活配置
  set_active.py --show       # 显示当前激活
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    PROJECT_ROOT,
    CONTROL_ROOT,
    ACTIVE_FILE,
    list_active_task_dirs,
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def show_current() -> int:
    rel = ACTIVE_FILE.relative_to(PROJECT_ROOT)
    if not ACTIVE_FILE.exists():
        print(f"当前未设置激活总控。配置文件：{rel}（不存在）")
        return 0
    content = ACTIVE_FILE.read_text(encoding="utf-8").strip()
    candidates = list_active_task_dirs()
    valid = any(d.name == content for d in candidates)
    suffix = "" if valid else "（⚠ 任务不在活跃列表中，可能已归档或重命名）"
    print(f"当前激活总控：{content}{suffix}")
    print(f"配置文件：{rel}")
    return 0 if valid else 4


def clear_active() -> int:
    rel = ACTIVE_FILE.relative_to(PROJECT_ROOT)
    if ACTIVE_FILE.exists():
        ACTIVE_FILE.unlink()
        print(f"已清除：{rel}")
    else:
        print(f"配置文件不存在，无需清除：{rel}")
    return 0


def set_active(keyword: str) -> int:
    candidates = list_active_task_dirs()
    if not candidates:
        print(f"未发现活跃总控目录（{CONTROL_ROOT.relative_to(PROJECT_ROOT)} 下没有含 README.md 的子目录）。")
        print("提示：先运行 bootstrap_project.py 初始化骨架，再用 task-control-doc skill 创建任务。")
        return 1
    key = normalize(keyword)
    matched = [d for d in candidates if key in normalize(d.name)]
    if not matched:
        print(f"未找到匹配关键词 '{keyword}' 的总控。候选：")
        for d in candidates:
            print(f"  - {d.name}")
        return 2
    if len(matched) > 1:
        print(f"关键词 '{keyword}' 匹配多个总控，请补充更具体的关键词：")
        for d in matched:
            print(f"  - {d.name}")
        return 3
    target = matched[0]
    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(target.name + "\n", encoding="utf-8")
    print(f"已设置激活总控：{target.name}")
    print(f"配置文件：{ACTIVE_FILE.relative_to(PROJECT_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--clear", action="store_true", help="清除当前激活配置")
    group.add_argument("--show", action="store_true", help="显示当前激活配置")
    parser.add_argument("keyword", nargs="?", help="任务关键词（任务目录名片段）")
    args = parser.parse_args()

    if args.clear:
        return clear_active()
    if args.show:
        return show_current()
    if not args.keyword:
        parser.error("请提供关键词，或使用 --clear / --show")
    return set_active(args.keyword)


if __name__ == "__main__":
    sys.exit(main())
