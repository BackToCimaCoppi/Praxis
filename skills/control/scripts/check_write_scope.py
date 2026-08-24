#!/usr/bin/env python3
"""校验总控子任务候选提交没有越出工作包写入范围。"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(detail or f"git {' '.join(args)} 失败")
    return result.stdout


def normalize_path(raw: str) -> str:
    value = raw.strip().replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"非法仓库相对路径：{raw}")
    return path.as_posix()


def path_matches(path: str, rule: str) -> bool:
    rule = normalize_path(rule)
    if rule.endswith("/**"):
        prefix = rule[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if any(char in rule for char in "*?["):
        return fnmatch.fnmatchcase(path, rule)
    return path == rule


def parse_cross_rules(values: list[str]) -> dict[str, set[str]]:
    parsed: dict[str, set[str]] = defaultdict(set)
    for value in values:
        if "::" not in value:
            raise ValueError(
                f"跨任务例外必须精确到 Markdown 标题（path::标题）：{value}"
            )
        raw_path, heading = value.split("::", 1)
        heading = heading.strip()
        if not heading:
            raise ValueError(f"跨任务例外缺 Markdown 标题：{value}")
        parsed[normalize_path(raw_path)].add(heading)
    return parsed


def commit_parents(repo: Path, commit: str) -> list[str]:
    line = git(repo, "rev-list", "--parents", "-n", "1", commit).strip()
    parts = line.split()
    if not parts:
        raise ValueError(f"候选提交不存在：{commit}")
    return parts[1:]


def changed_paths(repo: Path, parent: str, commit: str) -> set[str]:
    output = git(
        repo,
        "-c",
        "core.quotePath=false",
        "diff",
        "--name-status",
        "--find-renames",
        parent,
        commit,
        "--",
    )
    paths: set[str] = set()
    for raw in output.splitlines():
        cells = raw.split("\t")
        if len(cells) < 2:
            continue
        status = cells[0]
        names = cells[1:]
        if status.startswith(("R", "C")) and len(names) == 2:
            paths.update(normalize_path(name) for name in names)
        else:
            paths.add(normalize_path(names[-1]))
    return paths


def show_file(repo: Path, commit: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(f"跨任务段例外不允许新增、删除或重命名文件：{path}")
    return result.stdout


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def outside_allowed_sections(text: str, titles: set[str], path: str) -> str:
    lines = text.splitlines(keepends=True)
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.rstrip("\r\n"))
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))

    ranges: list[tuple[int, int]] = []
    for title in sorted(titles):
        matches = [(idx, level) for idx, level, name in headings if name == title]
        if len(matches) != 1:
            raise ValueError(
                f"{path} 中标题“{title}”应恰好出现一次，实际 {len(matches)} 次"
            )
        start, level = matches[0]
        end = len(lines)
        for idx, next_level, _ in headings:
            if idx > start and next_level <= level:
                end = idx
                break
        ranges.append((start + 1, end))

    masked = list(lines)
    for start, end in sorted(ranges, reverse=True):
        masked[start:end] = ["<ALLOWED_SECTION_BODY>\n"]
    return "".join(masked)


def validate_section_change(
    repo: Path, parent: str, commit: str, path: str, titles: set[str]
) -> None:
    before = show_file(repo, parent, path)
    after = show_file(repo, commit, path)
    before_outside = outside_allowed_sections(before, titles, path)
    after_outside = outside_allowed_sections(after, titles, path)
    if before_outside != after_outside:
        joined = "、".join(sorted(titles))
        raise ValueError(f"{path} 在允许标题之外发生变化（仅允许：{joined}）")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="校验明确的子任务候选提交是否越出允许写入路径"
    )
    parser.add_argument("--repo", default=".", help="Git 仓库根或其子目录")
    parser.add_argument("--start-commit", required=True, help="子任务开工提交")
    parser.add_argument(
        "--candidate", action="append", required=True, help="本子任务候选提交，可重复"
    )
    parser.add_argument(
        "--allow", action="append", default=[], help="允许写入的仓库相对路径/glob，可重复"
    )
    parser.add_argument(
        "--allow-cross",
        action="append",
        default=[],
        help="跨任务 Markdown 段例外，格式 path::标题，可重复",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repo = Path(git(Path(args.repo).resolve(), "rev-parse", "--show-toplevel").strip())
        start = git(repo, "rev-parse", "--verify", f"{args.start_commit}^{{commit}}").strip()
        allowed = [normalize_path(value) for value in args.allow]
        cross = parse_cross_rules(args.allow_cross)
        if not allowed and not cross:
            raise ValueError("至少声明一个 --allow 或 --allow-cross")

        violations: list[str] = []
        checked_paths: set[str] = set()
        for raw_candidate in args.candidate:
            candidate = git(
                repo, "rev-parse", "--verify", f"{raw_candidate}^{{commit}}"
            ).strip()
            ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", start, candidate], cwd=repo
            )
            if ancestry.returncode != 0 or candidate == start:
                violations.append(
                    f"候选 {candidate[:12]} 不在 start_commit {start[:12]} 之后"
                )
                continue
            parents = commit_parents(repo, candidate)
            if len(parents) != 1:
                violations.append(f"候选 {candidate[:12]} 必须是单父提交")
                continue
            parent = parents[0]
            for path in sorted(changed_paths(repo, parent, candidate)):
                checked_paths.add(path)
                if any(path_matches(path, rule) for rule in allowed):
                    continue
                if path in cross:
                    try:
                        validate_section_change(repo, parent, candidate, path, cross[path])
                    except ValueError as exc:
                        violations.append(f"候选 {candidate[:12]}：{exc}")
                    continue
                violations.append(f"候选 {candidate[:12]}：越界路径 {path}")

        if violations:
            print("FAIL 写入范围检查")
            for violation in violations:
                print(f"- {violation}")
            return 1
        print(
            f"PASS 写入范围检查：{len(args.candidate)} 个候选提交，"
            f"{len(checked_paths)} 个变更路径"
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR 写入范围检查：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
