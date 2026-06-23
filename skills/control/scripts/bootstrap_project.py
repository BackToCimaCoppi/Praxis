#!/usr/bin/env python3
"""
新项目初始化：建好 control skill 约定的项目内骨架（幂等）。

会建：
- docs/00-任务总控/README.md（活跃任务索引模板）
- docs/00-任务总控/归档/README.md（归档总索引模板）
- .gitignore 中追加 .claude/local/（若未包含）

不会覆盖已存在的文件。重复运行无副作用。

不会建：
- 任务子目录（用 task-control-doc skill 创建）
- 06-09 等价的规范文档（方法论真值在 ~/.claude/skills/control/references/总控规范.md）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_ROOT, CONTROL_ROOT, ARCHIVE_ROOT

GITIGNORE = PROJECT_ROOT / ".gitignore"


ACTIVE_README_TEMPLATE = """# 当前项目任务总控

> 本目录是 control skill 的固定路径。所有任务总控文档放在这里。
> 详细规范见 control skill 的 `references/总控规范.md`（用户级，跨项目通用）。

## 当前活跃任务

| 任务目录 | 任务名 | 状态 | 备注 |
| --- | --- | --- | --- |

（暂无活跃任务）

## 已归档任务

详见 [`归档/`](归档/README.md)。

## 操作指南

- 创建新总控：`task-control-doc` skill
- 进入活跃总控：`/control <关键词>`
- 列所有活跃：`/control list`
- 归档完成的总控：通过 `archive_control.py --apply`
"""


ARCHIVE_README_TEMPLATE = """# 归档总索引

> 已完成的任务总控按主版本归档到此目录下。

## 版本列表

（暂无归档版本）

新归档时按版本（V1 / V2 / ...）建子目录，并将整个任务目录迁入。
归档由 `archive_control.py --apply` 自动同步。
"""


GITIGNORE_CANONICAL = ".claude/local/"
GITIGNORE_VARIANTS = {
    ".claude/local/",
    ".claude/local",
    "/.claude/local/",
    "/.claude/local",
}


def write_if_absent(path: Path, content: str) -> str:
    """文件不存在则写入，返回 'created' / 'skipped'。"""
    if path.exists():
        return "skipped"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "created"


def ensure_gitignore_entry() -> str:
    """确保 .gitignore 包含 .claude/local/，返回 'created' / 'added' / 'present'。"""
    if not GITIGNORE.exists():
        GITIGNORE.write_text(GITIGNORE_CANONICAL + "\n", encoding="utf-8")
        return "created"
    text = GITIGNORE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip() in GITIGNORE_VARIANTS:
            return "present"
    suffix = "" if text.endswith("\n") else "\n"
    GITIGNORE.write_text(text + suffix + GITIGNORE_CANONICAL + "\n", encoding="utf-8")
    return "added"


def main() -> int:
    print(f"项目根：{PROJECT_ROOT}")
    print()

    actions: list[tuple[str, str]] = []

    p = CONTROL_ROOT / "README.md"
    actions.append((str(p.relative_to(PROJECT_ROOT)), write_if_absent(p, ACTIVE_README_TEMPLATE)))

    p = ARCHIVE_ROOT / "README.md"
    actions.append((str(p.relative_to(PROJECT_ROOT)), write_if_absent(p, ARCHIVE_README_TEMPLATE)))

    actions.append((".gitignore（含 .claude/local/）", ensure_gitignore_entry()))

    label_map = {
        "created": "✓ 新建",
        "added":   "✓ 追加",
        "skipped": "  跳过（已存在）",
        "present": "  跳过（已包含）",
    }

    print("初始化结果：")
    for path, action in actions:
        print(f"  {label_map[action]}  {path}")

    print()
    if all(a in ("skipped", "present") for _, a in actions):
        print("所有骨架已就绪，本次无变更。")
    else:
        print("初始化完成。下一步：用 task-control-doc skill 创建第一个总控任务。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
