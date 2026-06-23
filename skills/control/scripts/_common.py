"""control skill 脚本共享工具。

模块加载时即定位项目根（通过 CLAUDE_PROJECT_DIR 或 git rev-parse），
所有脚本通过 import 此模块得到统一的路径常量。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ARCHIVE_DIR_NAME = "归档"
MAIN_DOC_NAME = "README.md"


def find_project_root() -> Path:
    """定位当前项目根目录。

    优先级：
    1. CLAUDE_PROJECT_DIR 环境变量
    2. git rev-parse --show-toplevel
    3. 报错（脚本必须在 git 仓库内执行）
    """
    if env := os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(env)
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if output:
            return Path(output)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    raise SystemExit(
        "control skill 必须在 git 仓库内执行"
        "（或设置 CLAUDE_PROJECT_DIR 环境变量）"
    )


PROJECT_ROOT = find_project_root()
CONTROL_ROOT = PROJECT_ROOT / "docs/00-任务总控"
ARCHIVE_ROOT = CONTROL_ROOT / ARCHIVE_DIR_NAME
ACTIVE_FILE = PROJECT_ROOT / ".claude/local/active-control"


def has_main_doc(task_dir: Path) -> bool:
    return (task_dir / MAIN_DOC_NAME).exists()


def find_main_doc(task_dir: Path) -> Path | None:
    p = task_dir / MAIN_DOC_NAME
    return p if p.exists() else None


def list_active_task_dirs() -> list[Path]:
    """扫描 docs/00-任务总控/ 下所有活跃任务目录（含 README.md，排除归档）。"""
    if not CONTROL_ROOT.exists():
        return []
    return sorted(
        d for d in CONTROL_ROOT.iterdir()
        if d.is_dir() and d.name != ARCHIVE_DIR_NAME and has_main_doc(d)
    )


def read_active_control() -> str | None:
    """读 .claude/local/active-control 文件内容（任务目录精确名）。"""
    if not ACTIVE_FILE.exists():
        return None
    content = ACTIVE_FILE.read_text(encoding="utf-8").strip()
    return content or None


# ---------------------------------------------------------------------------
# 子任务两级层次：共享判定与派生
# ---------------------------------------------------------------------------

STATUS_ENUM = ("待完成", "进行中", "已完成", "阻塞", "已取消")
PARENT_STATUS_PLACEHOLDER = "派生"  # 父行状态列固定占位


def is_parent_seq(seq: str, all_seqs: set[str]) -> bool:
    """该编号是否是有子任务的父：存在以 `seq + '.'` 开头的其他编号。"""
    prefix = seq + "."
    return any(s != seq and s.startswith(prefix) for s in all_seqs)


def is_child_seq(seq: str) -> bool:
    """该编号是否是二级子任务（含 `.`）。"""
    return "." in seq


def direct_children(parent_seq: str, all_seqs: list[str]) -> list[str]:
    """返回直接子任务编号（按出现顺序）。只支持两级。"""
    prefix = parent_seq + "."
    return [s for s in all_seqs if s.startswith(prefix)]


def derive_status_from_counts(status_counts: dict[str, int]) -> str:
    """从状态计数派生综合状态。
    优先级：阻塞 > 进行中 > 未启动 > 已完成（全 已完成/已取消）。
    空集合返回 "空"。
    """
    total = sum(status_counts.values())
    if total == 0:
        return "空"
    if status_counts.get("阻塞", 0) > 0:
        return "阻塞"
    if status_counts.get("进行中", 0) > 0:
        return "进行中"
    settled = status_counts.get("已完成", 0) + status_counts.get("已取消", 0)
    if settled == total:
        return "已完成"
    if status_counts.get("待完成", 0) == total:
        return "未启动"
    return "进行中"


def find_subtask_md(task_dir: Path, seq: str) -> Path | None:
    """定位拆分模式下的子任务工作包文件。返回 None 表示无对应文件（应回退到单文件模式）。

    布局规则：
    - `T1.1` 类子任务 → 优先 `<task_dir>/T1/T1.1-*.md`
    - `T1` 类（普通叶子或父任务）：
        - 优先 `<task_dir>/T1-*.md`（普通叶子工作包）
        - 否则 `<task_dir>/T1/T1.md`（被拆过的父任务文件）
    """
    if "." in seq:
        parent = seq.split(".", 1)[0]
        candidate = next((task_dir / parent).glob(f"{seq}-*.md"), None) if (task_dir / parent).is_dir() else None
        if candidate:
            return candidate
        return next(task_dir.glob(f"{seq}-*.md"), None)
    leaf_candidate = next(task_dir.glob(f"{seq}-*.md"), None)
    if leaf_candidate:
        return leaf_candidate
    parent_doc = task_dir / seq / f"{seq}.md"
    return parent_doc if parent_doc.is_file() else None


def expand_dep_to_leaves(dep: str, all_seqs: list[str]) -> list[str]:
    """把依赖编号展开为叶子集合。
    - 依赖一个父 → 展开为它所有直接子
    - 依赖一个叶子 → 原样返回
    - 找不到 → 原样返回（外层判定为未满足）
    """
    seqs_set = set(all_seqs)
    if dep not in seqs_set:
        return [dep]
    if is_parent_seq(dep, seqs_set):
        return direct_children(dep, all_seqs)
    return [dep]
