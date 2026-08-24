---
name: commit-changes
description: 仅手动触发。用户明确要求暂存、提交或推送时，先跑项目提交前门禁（若有），审查 diff，逐文件精确 stage 并等用户确认，再按项目提交规范写中文提交信息；禁止 git add -A 和 git add .；未明确要求不推送。触发词："提交"、"commit"、"push"、"推送"、"帮我提交"。
---

# Commit Changes

用户明确要求提交、推送或说"帮我提交"时使用。本 skill 是用户级通用引擎：只固定流程与红线；提交规范原文、门禁脚本、额外前缀规则由项目注入，本 skill 不硬编码任何项目值。

## 项目注入（挂载点）

| 槽位 | 来源（按顺序探测，先命中先用） | 缺省 |
|---|---|---|
| 提交规范原文 | 项目指令文件（`CLAUDE.md` / `AGENTS.md`）的「提交规范」节 → `CONTRIBUTING.md` | 本 skill「Rules」的默认格式 |
| 提交前门禁命令 | 项目补丁 skill 显式声明的命令 → `.claude/hooks/pre-handoff-check.sh` → `.claude/hooks/pre-commit-check.sh` | 无门禁，跳过 Step 0 |
| 额外首行规则 | 提交规范里声明的特殊前缀（如跨域提交标记、任务编号） | 无 |

## Required reads

1. 上表命中的提交规范原文——每次都读，不凭记忆写格式。

## Rules

- 提交信息用简体中文，格式 `<类型>: <简要描述>`；项目提交规范另有规定时以项目为准
- 提交前必须读 diff
- 未经用户明确要求，不 amend、不 force-push、不 push
- 不提交自己不理解、与本次任务无关的改动
- 永远不用 `git add -A` / `git add .`

## Default flow

### Step 0 — 门禁（项目有门禁脚本时必跑，不可跳过）

```bash
# 按挂载点顺序探测；命中哪条跑哪条，全部不存在则跳过本步
bash .claude/hooks/pre-handoff-check.sh
```

- 退出码非 0 → 立即停止，告知用户失败项，等修复后再触发本 skill
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

默认格式：`<类型>: <简要描述>`，类型限：`修复` / `功能` / `重构` / `规范` / `文档` / `配置`。

项目提交规范声明了额外首行规则时优先遵守（例：一次提交改动多个业务域目录时，首行用项目规定的跨域标记并说明原因）。

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
