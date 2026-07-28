#!/usr/bin/env python3
"""WCAG contrast self-check for doc-html-style semantic color tokens.

用途：写完一套语义色 token 后，把每个"文字色-背景色"组合喂给这个脚本，
跑出对比度数值和 pass/fail 判定，浅色模式和深色模式都要单独跑一遍。

用法：
    python3 check_contrast.py --file pairs.json
    python3 check_contrast.py "ink on surface=#1b2333,#ffffff,body" "badge=#ffffff,#b4780a,large"

pairs.json 格式（列表，每项一个组合）：
    [
      {"name": "ink on surface (light)", "fg": "#1b2333", "bg": "#ffffff", "role": "body"},
      {"name": "badge text on status-doing (light)", "fg": "#ffffff", "bg": "#b4780a", "role": "large"}
    ]

role: "body"（正文，阈值4.5:1，默认） | "large"（大字/图形/徽章文字，阈值3:1）

任一组合判定为 fail 时，脚本以退出码 1 结束，方便当自检口令直接跑。
"""

import sys
import json
import argparse

THRESHOLDS = {"body": 4.5, "large": 3.0}


def parse_hex(color):
    s = color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"无法解析颜色值：{color!r}，需要 #rgb 或 #rrggbb 形式")
    r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    return r, g, b


def _linearize(c):
    c = c / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    r, g, b = rgb
    r, g, b = _linearize(r), _linearize(g), _linearize(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex, bg_hex):
    l1 = relative_luminance(parse_hex(fg_hex))
    l2 = relative_luminance(parse_hex(bg_hex))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def parse_inline_pair(spec):
    # 格式：name=fg,bg[,role]
    if "=" not in spec:
        raise ValueError(f"格式应为 name=fg,bg[,role]，实际收到：{spec!r}")
    name, rest = spec.split("=", 1)
    parts = [p.strip() for p in rest.split(",")]
    if len(parts) not in (2, 3):
        raise ValueError(f"格式应为 name=fg,bg[,role]，实际收到：{spec!r}")
    fg, bg = parts[0], parts[1]
    role = parts[2] if len(parts) == 3 else "body"
    return {"name": name.strip(), "fg": fg, "bg": bg, "role": role}


def load_pairs(args):
    pairs = []
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            pairs.extend(json.load(f))
    for spec in args.pairs:
        pairs.append(parse_inline_pair(spec))
    return pairs


def main():
    ap = argparse.ArgumentParser(description="WCAG contrast self-check for doc-html-style tokens")
    ap.add_argument("pairs", nargs="*", help='内联组合，格式 name=fg,bg[,role]')
    ap.add_argument("--file", help="JSON 文件路径，内容见脚本头部说明")
    args = ap.parse_args()

    try:
        pairs = load_pairs(args)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"输入格式错误：{e}", file=sys.stderr)
        return 2
    if not pairs:
        print(__doc__)
        return 0

    rows = []
    any_fail = False
    for p in pairs:
        role = p.get("role", "body")
        if role not in THRESHOLDS:
            print(f"未知 role：{role!r}，只接受 body/large", file=sys.stderr)
            return 2
        try:
            ratio = contrast_ratio(p["fg"], p["bg"])
        except ValueError as e:
            print(f"输入格式错误（{p.get('name', '?')}）：{e}", file=sys.stderr)
            return 2
        threshold = THRESHOLDS[role]
        passed = ratio >= threshold
        any_fail = any_fail or not passed
        rows.append((p["name"], p["fg"], p["bg"], role, ratio, threshold, passed))

    name_w = max(4, max(len(r[0]) for r in rows))
    header = f"{'名称':<{name_w}}  文字色     背景色     角色     对比度   阈值   判定"
    print(header)
    print("-" * len(header))
    for name, fg, bg, role, ratio, threshold, passed in rows:
        verdict = "PASS" if passed else "FAIL"
        print(f"{name:<{name_w}}  {fg:<9} {bg:<9} {role:<7}  {ratio:5.2f}:1  {threshold:>3.1f}:1  {verdict}")

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
