#!/usr/bin/env bash
# doc-length-check.sh — 长文档行数治理扫描
# 用法: doc-length-check.sh [--config <path>] [--format human|json] [--scope all|<file>...]
# 退出码: 0=全通过 1=有WARNING 2=有CRITICAL（均不阻断调用方流程）

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CONFIG="$SCRIPT_DIR/doc-length-config.default.json"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PROJECT_CONFIG="$PROJECT_DIR/.claude/doc-length-config.json"

FORMAT="human"
CUSTOM_CONFIG=""
SCOPE_ALL=false
SCOPE_FILES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --format)
            FORMAT="$2"
            shift 2
            ;;
        --config)
            CUSTOM_CONFIG="$2"
            shift 2
            ;;
        --scope)
            shift
            while [[ $# -gt 0 ]] && [[ "$1" != --* ]]; do
                if [[ "$1" == "all" ]]; then
                    SCOPE_ALL=true
                else
                    SCOPE_FILES+=("$1")
                fi
                shift
            done
            ;;
        *)
            shift
            ;;
    esac
done

EFFECTIVE_CONFIG="${CUSTOM_CONFIG:-$PROJECT_CONFIG}"

python3 - \
    "$FORMAT" \
    "$DEFAULT_CONFIG" \
    "$EFFECTIVE_CONFIG" \
    "$SCOPE_ALL" \
    ${SCOPE_FILES[@]+"${SCOPE_FILES[@]}"} << 'PYEOF'
import sys, json, os, subprocess

format_out = sys.argv[1]
default_cfg_path = sys.argv[2]
project_cfg_path = sys.argv[3]
scope_all = sys.argv[4] == "true"
scope_files = [f for f in sys.argv[5:] if f]

# Determine project root
project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
if not project_dir:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
        project_dir = r.stdout.strip() if r.returncode == 0 else os.getcwd()
    except Exception:
        project_dir = os.getcwd()

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

default_cfg = load_json(default_cfg_path)
proj_cfg = load_json(project_cfg_path)

thresholds = default_cfg.get("thresholds", {
    "api-schema-test": {"warn": 600, "crit": 1000},
    "design-doc": {"warn": 800, "crit": 1500}
})
for k, v in proj_cfg.get("thresholds_override", {}).items():
    thresholds[k] = v

extra_excludes = proj_cfg.get("exclude_globs_extra", [])

def classify(filepath):
    p = filepath.replace("\\", "/")
    parts = p.split("/")
    basename = parts[-1] if parts else ""

    # Skip agent rules
    if basename in ("CLAUDE.md", "AGENTS.md"):
        return "skip"
    if basename == "SKILL.md" and "skills" in parts:
        return "skip"

    # Skip default excluded dirs
    skip_dirs = {"09-归档", "node_modules", ".git", "backups", "worktrees", "results"}
    if any(part in skip_dirs for part in parts):
        return "skip"

    # Skip project extra excludes (clean pattern to substring)
    for exc in extra_excludes:
        exc_clean = exc.replace("/**", "").replace("**/", "").replace("/*.md", "").replace("*.md", "")
        if exc_clean and exc_clean in p:
            return "skip"

    # api-schema-test（七层：L3 接口契约 / L4 数据库 / L7 测试）
    is_api = (
        "03-接口契约" in parts or
        "04-数据库" in parts or
        "07-测试" in parts
    )
    if is_api:
        return "api-schema-test"

    # design-doc（七层：L1 需求 / L2 交互规格 / L5 前端技术 / L6 后端技术 / 任务总控）
    is_design = (
        "01-需求" in parts or
        "02-交互规格" in parts or
        "05-前端技术" in parts or
        "06-后端技术" in parts or
        ("00-任务总控" in parts and "归档" not in parts) or
        any(kw in basename for kw in ["施工蓝图", "任务总控", "技术方案"])
    )
    if is_design:
        return "design-doc"

    return "skip"

def count_lines(filepath):
    try:
        full_path = filepath if os.path.isabs(filepath) else os.path.join(project_dir, filepath)
        with open(full_path, "r", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

if scope_all:
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, cwd=project_dir
        )
        all_files = [f for f in r.stdout.splitlines() if f.endswith(".md") and f.strip()]
    except Exception:
        all_files = []
else:
    all_files = [f for f in scope_files if f.endswith(".md")]

results_critical = []
results_warning = []
scanned = 0

for f in all_files:
    ftype = classify(f)
    if ftype == "skip":
        continue
    scanned += 1
    thresh = thresholds.get(ftype, {"warn": 99999, "crit": 99999})
    lines = count_lines(f)
    entry = {"path": f, "lines": lines, "type": ftype}
    if lines >= thresh["crit"]:
        results_critical.append(entry)
    elif lines >= thresh["warn"]:
        results_warning.append(entry)

exit_code = 2 if results_critical else (1 if results_warning else 0)

if format_out == "json":
    out = {"critical": results_critical, "warning": results_warning, "scanned": scanned}
    print(json.dumps(out, ensure_ascii=False, indent=2))
else:
    if not results_critical and not results_warning:
        if scanned > 0:
            print(f"✓ 扫描 {scanned} 份文档，全部在阈值范围内。")
    else:
        print(f"=== 长文档治理扫描（共扫 {scanned} 份）===")
        for e in sorted(results_critical, key=lambda x: -x["lines"]):
            print(f"[CRITICAL] {e['lines']:>5} 行  {e['type']:<20}  {e['path']}")
        for e in sorted(results_warning, key=lambda x: -x["lines"]):
            print(f"[WARNING]  {e['lines']:>5} 行  {e['type']:<20}  {e['path']}")
        if results_critical:
            print()
            print("CRITICAL 文档若本轮做了实质修改 → 调用 long-doc-governance skill 治理。")
        if results_warning:
            print("WARNING  仅提示，不必当轮处理。")

sys.exit(exit_code)
PYEOF
