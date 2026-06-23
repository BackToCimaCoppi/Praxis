---
name: commit-changes
description: Use when the user wants to stage changes, create a git commit, or push to the remote repository. Follow the repository's Chinese commit-message convention and review the diff before committing. Run the repository's pre-commit check if present before staging. Never use git add -A or git add .
---

# Commit Changes

Use this skill when the user asks to commit, push, or "帮我提交".

## Required reads

1. 项目的提交规范文档（如 `CLAUDE.md` / `CONTRIBUTING.md`）

## Rules

- Use Simplified Chinese commit messages
- Format the message as `<类型>: <简要描述>`
- Review the diff before committing
- Do not amend or force-push unless the user explicitly asks
- Do not commit unrelated work you do not understand
- Never use `git add -A` or `git add .`

## Default flow

### Step 0 — 门禁（可选；项目有提交前门禁脚本时先跑，不可跳过）

```bash
# 若项目存在提交前门禁脚本（如 .claude/hooks/pre-commit-check.sh）则先运行；没有则跳过本步
bash .claude/hooks/pre-commit-check.sh
```

- exit 1 → 立即停止，告知用户检查失败项，等修复后再触发 skill
- `[WARN]` 输出 → 记录警告，在 Report back 中提及，不阻断流程

### Step 1 — 确认变更文件清单

```bash
git status --short
```

读取输出，理解当前工作区状态（哪些是 tracked 修改、哪些是 untracked 新文件）。

### Step 2 — 阅读 diff，理解改动性质

```bash
git diff
git diff --cached
```

判断：改动主题（功能/修复/文档/重构/规范/配置）、涉及模块、是否含无关改动需拆分。

### Step 3 — 拟定 stage 清单并等待确认

> [!CAUTION]
> 禁止 `git add -A` 或 `git add .`。必须逐文件或逐目录精确 stage。

列出拟 stage 的文件清单（`git add <具体路径>` 形式），明确告知用户并等待确认，用户确认后再执行 stage。

### Step 4 — 拟写 commit message

格式：`<类型>: <简要描述>`

类型限：`修复` / `功能` / `重构` / `规范` / `文档` / `配置`

### Step 5 — 执行提交

```bash
git commit -m "<commit message>"
```

### Step 6 — 推送（仅在用户明确要求时执行）

用户未说"push"或"推送"时，不自动推送。

## Report back

用中文总结：

- staged 了哪些文件（列出完整路径）
- commit message 是什么
- 是否已 push
- 若门禁脚本有 `[WARN]` 输出，说明具体警告内容
- 若接口面有变更但未更新测试脚本，说明原因
