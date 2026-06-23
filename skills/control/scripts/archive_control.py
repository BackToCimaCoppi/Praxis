#!/usr/bin/env python3
"""
归档总控任务：自动同步 3 处索引并迁移目录到 归档/V{x}/。

按 `~/.claude/skills/control/references/总控规范.md` §5 索引同步表执行：
1. 顶层 docs/00-任务总控/README.md 删除活跃任务行
2. 迁移目录到 docs/00-任务总控/归档/V{x}/{任务目录名}/
3. docs/00-任务总控/归档/README.md 增加该任务的归档登记
4. docs/00-任务总控/归档/V{x}/README.md 增加该任务的版本登记

默认 dry-run，加 --apply 才真正写入。
归档完后如该任务有专属 git worktree，请手动 `git worktree remove`。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    PROJECT_ROOT,
    CONTROL_ROOT,
    ARCHIVE_ROOT,
    list_active_task_dirs,
    find_main_doc,
    is_parent_seq,
)


README = CONTROL_ROOT / "README.md"
ARCHIVE_README = ARCHIVE_ROOT / "README.md"


@dataclass
class Plan:
    task_dir: Path
    task_name: str
    version: str
    reason: str
    archive_target: Path
    archive_version_dir: Path
    archive_version_readme: Path
    readme_row_match: str | None


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def find_task_dir(keyword: str) -> Path:
    key = normalize(keyword)
    candidates = [d for d in list_active_task_dirs() if key in normalize(d.name)]
    if not candidates:
        raise SystemExit(f"未找到匹配关键词 '{keyword}' 的活跃任务目录")
    if len(candidates) > 1:
        names = "\n  ".join(d.name for d in candidates)
        raise SystemExit(f"匹配到多个任务目录，请用更具体关键词：\n  {names}")
    return candidates[0]


def find_control_doc(task_dir: Path) -> Path:
    main = find_main_doc(task_dir)
    if not main:
        raise SystemExit(f"未找到 {task_dir.name}/README.md")
    return main


def check_all_completed(doc: Path) -> list[str]:
    """返回未完成叶子子任务编号列表。空 = 全部叶子完成。

    两级层次：父任务（有子的 Tn）状态为派生量，不参与校验；只校验叶子。
    """
    lines = doc.read_text(encoding="utf-8").splitlines()
    in_table = False
    header_idx: dict[str, int] = {}
    rows: list[tuple[str, str]] = []  # (seq, status)
    for raw in lines:
        line = raw.strip()
        if re.fullmatch(r"#+\s*(\d+\.\s*)?子任务总表", line):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if header_idx:
                break
            continue
        if re.fullmatch(r"\|\s*-+\s*(\|\s*-+\s*)+\|?", line):
            continue
        cells = [c.strip().replace("`", "").strip() for c in line.strip("|").split("|")]
        if not header_idx:
            for i, c in enumerate(cells):
                if c in {"编号", "序号"}:
                    header_idx["seq"] = i
                if c in {"状态", "当前状态"}:
                    header_idx["status"] = i
            if "seq" not in header_idx or "status" not in header_idx:
                raise SystemExit(f"子任务总表缺少必要列: {cells}")
            continue
        if header_idx["status"] >= len(cells):
            continue
        status = cells[header_idx["status"]]
        seq = cells[header_idx["seq"]] if header_idx["seq"] < len(cells) else "?"
        rows.append((seq, status))

    all_seqs = {s for s, _ in rows}
    issues: list[str] = []
    for seq, status in rows:
        if is_parent_seq(seq, all_seqs):
            continue  # 父任务派生，跳过
        if status not in {"已完成", "已取消"}:
            issues.append(f"{seq}: {status}")
    return issues


def find_row_in_active_section(path: Path, task_dir_name: str) -> str | None:
    """在顶层 README 的「当前活跃任务」段范围内匹配任务行。"""
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    in_active_section = False
    for line in lines:
        stripped = line.strip()
        if not in_active_section:
            if "当前活跃任务" in stripped:
                in_active_section = True
            continue
        if stripped.startswith("## "):
            break
        if any(marker in stripped for marker in ("已结束活跃推进", "已归档", "已删除")):
            break
        if line.lstrip().startswith("|") and task_dir_name in line:
            return line
    return None


def remove_line(path: Path, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text = "\n".join(l for l in text.splitlines() if l != line)
    if not new_text.endswith("\n"):
        new_text += "\n"
    path.write_text(new_text, encoding="utf-8")


def append_to_archive_readme(version: str, task_dir_name: str, reason: str) -> None:
    """在 归档/README.md 的版本段下追加新归档登记。

    规则：找形如 `## V{x}` 的标题，在它下面追加一行；
    若没有该版本段，追加一个新段到文件末尾。
    """
    if not ARCHIVE_README.exists():
        return
    text = ARCHIVE_README.read_text(encoding="utf-8")
    if task_dir_name in text:
        return
    bullet = f"- `{task_dir_name}/`：{reason}"
    # 首次归档时移除 bootstrap 模板里的"（暂无归档版本）"占位
    lines = [l for l in text.splitlines() if l.strip() != "（暂无归档版本）"]
    out: list[str] = []
    inserted = False
    in_target_version = False
    version_header_pat = re.compile(rf"^##\s+{re.escape(version)}\b")
    other_section_pat = re.compile(r"^##\s+\S")
    for line in lines:
        if not inserted and version_header_pat.match(line):
            in_target_version = True
            out.append(line)
            continue
        if in_target_version and other_section_pat.match(line):
            out.append(bullet)
            out.append("")
            inserted = True
            in_target_version = False
        out.append(line)
    if not inserted:
        if in_target_version:
            out.append(bullet)
            inserted = True
        else:
            if out and out[-1].strip():
                out.append("")
            out.append(f"## {version}")
            out.append("")
            out.append(bullet)
    ARCHIVE_README.write_text("\n".join(out) + "\n", encoding="utf-8")


def append_to_version_readme(version_readme: Path, task_dir_name: str, reason: str) -> None:
    if not version_readme.exists():
        return
    text = version_readme.read_text(encoding="utf-8")
    if task_dir_name in text:
        return
    bullet = f"- `{task_dir_name}/`：{reason}"
    if "归档清单" not in text:
        new_text = text.rstrip() + f"\n\n## 归档清单\n\n{bullet}\n"
    else:
        lines = text.splitlines()
        out: list[str] = []
        inserted = False
        in_list = False
        for line in lines:
            if not inserted and "归档清单" in line:
                in_list = True
                out.append(line)
                continue
            if in_list and line.strip().startswith("##"):
                out.append(bullet)
                inserted = True
                in_list = False
            out.append(line)
        if not inserted:
            out.append(bullet)
        new_text = "\n".join(out) + "\n"
    version_readme.write_text(new_text, encoding="utf-8")


def make_plan(keyword: str, version: str, reason: str) -> Plan:
    task_dir = find_task_dir(keyword)
    doc = find_control_doc(task_dir)

    issues = check_all_completed(doc)
    if issues:
        raise SystemExit(
            "归档校验失败，存在未完成子任务：\n  - " + "\n  - ".join(issues) +
            "\n\n所有子任务必须为 已完成 或 已取消 才能归档。"
        )

    version_dir = ARCHIVE_ROOT / version
    version_readme = version_dir / "README.md"

    return Plan(
        task_dir=task_dir,
        task_name=task_dir.name,
        version=version,
        reason=reason,
        archive_target=version_dir / task_dir.name,
        archive_version_dir=version_dir,
        archive_version_readme=version_readme,
        readme_row_match=find_row_in_active_section(README, task_dir.name),
    )


def print_plan(plan: Plan, apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] 归档计划：{plan.task_name} → {plan.version}")
    print(f"  归档目标：{plan.archive_target.relative_to(PROJECT_ROOT)}")
    if plan.readme_row_match:
        print(f"  ✓ 删除顶层 README.md 的「当前活跃任务」匹配行")
    else:
        print(f"  - 顶层 README.md 无匹配行（已是干净状态）")
    if plan.archive_version_dir.exists():
        print(f"  ✓ 迁移目录 → {plan.archive_target.relative_to(PROJECT_ROOT)}")
        print(f"  ✓ 在 {plan.archive_version_readme.relative_to(PROJECT_ROOT)} 增加登记")
    else:
        print(f"  ⚠ 版本目录 {plan.archive_version_dir.relative_to(PROJECT_ROOT)} 不存在，apply 时将自动建（含 README.md 模板）")
    print(f"  ✓ 在 归档/README.md 的「{plan.version}」段增加登记")


VERSION_README_TEMPLATE = """# {version} 归档索引

> 本版本归档的任务总控清单。

## 归档清单

"""


def ensure_version_readme(version_readme: Path, version: str) -> None:
    if version_readme.exists():
        return
    version_readme.parent.mkdir(parents=True, exist_ok=True)
    version_readme.write_text(VERSION_README_TEMPLATE.format(version=version), encoding="utf-8")


def apply_plan(plan: Plan) -> None:
    if plan.readme_row_match:
        remove_line(README, plan.readme_row_match)
    plan.archive_version_dir.mkdir(parents=True, exist_ok=True)
    ensure_version_readme(plan.archive_version_readme, plan.version)
    if plan.archive_target.exists():
        raise SystemExit(f"归档目标已存在：{plan.archive_target}")
    shutil.move(str(plan.task_dir), str(plan.archive_target))
    append_to_version_readme(plan.archive_version_readme, plan.task_name, plan.reason)
    append_to_archive_readme(plan.version, plan.task_name, plan.reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword", help="任务关键词（任务目录名片段）")
    parser.add_argument("--version", required=True, help="归档迭代版本，如 V1 / V2")
    parser.add_argument("--reason", default="任务完成归档", help="归档说明")
    parser.add_argument("--apply", action="store_true", help="真正执行（默认 dry-run）")
    args = parser.parse_args()

    plan = make_plan(args.keyword, args.version, args.reason)
    print_plan(plan, args.apply)
    if not args.apply:
        print("\n（dry-run，未写入。加 --apply 才真正执行。）")
        return 0

    apply_plan(plan)
    print("\n归档完成。如该任务有专属 worktree，请手动清理：")
    print(f"  git worktree list                    # 找到该任务对应的 worktree 路径")
    print(f"  git worktree remove <path>           # 移除 worktree")
    print(f"  git branch -d <branch>               # 删除分支（如已合并）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
