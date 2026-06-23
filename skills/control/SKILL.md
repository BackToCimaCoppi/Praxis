---
name: control
description: Use when the task is to inspect or continue an active master control document under docs/00-任务总控/, such as "继续总控", "执行 T3", "查看总控状态", "给我一个总控任务表". This skill selects the target task directory, reads MINIMAL mandatory context for the requested granularity, executes one subtask within strict scope, and writes status updates back. Strictly enforces single-subtask boundaries: executing Tn means doing ONLY Tn, never adjacent subtasks.
---

# Control

按当前项目 `docs/00-任务总控/` 下的总控文档推进任务。本 skill 是**通用方法论 skill**（用户级），不绑定具体项目。

**真值源**：`references/总控规范.md`（本 skill 内）。

---

## 🛑 执行边界（最高红线，永远遵守）

> 这是本 skill 最重要的一条。所有其他规则都让位于此。

1. 用户指定 `/control <key> Tn` → **只执行 Tn**（支持 `Tn.x` 二级子任务）。不做 Tn-1，不做 Tn+1，不做同级兄弟，不"顺手"做相关任务。
2. Tn 的「输出物」全部产出 → **立刻停止，回填状态，向用户报告**。等用户下一步指令。
3. ✅ 可以读其他子任务的产出物（依赖关系需要）
4. ❌ 不可写入其他子任务范围（即使发现"很容易顺便做"也不要做）
5. 如果发现 Tn 的范围定义有问题（应扩大或缩小） → **停止施工，向用户报告问题**，不要自行扩张
6. **过程资产边界**：执行 Tn 时产生的中间文档（设计稿、清单、批判稿等），只能写到 `_shared/` 且文件名带 `T{n}-` 前缀（任务级共享资产无前缀）；**不可**用其他子任务的 `T{m}-` 前缀（m≠n），**不可**平铺到任务根目录，**不可**新建 `_T{n}/` 目录（旧规则已废除，存量只读）。详见总控规范 §1.1.1。

---

## 项目约定

本 skill 假设当前项目遵循以下固定路径约定（所有项目通用，不带任何具体项目烙印）：

| 路径 | 用途 |
|---|---|
| `<PROJECT_ROOT>/docs/00-任务总控/` | 总控目录树根 |
| `<PROJECT_ROOT>/docs/00-任务总控/README.md` | 活跃任务索引 |
| `<PROJECT_ROOT>/docs/00-任务总控/归档/` | 已完成任务归档树 |
| `<PROJECT_ROOT>/docs/00-任务总控/归档/README.md` | 归档总索引 |
| `<PROJECT_ROOT>/docs/00-任务总控/归档/V{x}/README.md` | 版本归档索引 |
| `<PROJECT_ROOT>/docs/00-任务总控/{YYYY-MM-DD}-{任务名}/` | 任务子目录（**日期前缀防多 worktree 编号撞车**） |
| `<PROJECT_ROOT>/docs/00-任务总控/{YYYY-MM-DD}-{任务名}/README.md` | 任务主总控（拆分 / 单文件统一） |
| `<PROJECT_ROOT>/docs/00-任务总控/{YYYY-MM-DD}-{任务名}/T{n}-{子任务名}.md` | 拆分模式的一级子任务工作包 |
| `<PROJECT_ROOT>/docs/00-任务总控/{YYYY-MM-DD}-{任务名}/T{n}/T{n}.md` | **被拆过**的父任务说明（保留背景/范围，原 T{n}-*.md 迁移到此） |
| `<PROJECT_ROOT>/docs/00-任务总控/{YYYY-MM-DD}-{任务名}/T{n}/T{n}.{m}-{子任务名}.md` | 二级子任务工作包（split 后产生） |
| `<PROJECT_ROOT>/.claude/local/active-control` | per-worktree 激活配置（gitignored） |
| `<PROJECT_ROOT>/.gitignore` | 必须包含 `.claude/local/` |

**项目根解析**：脚本通过 `find_project_root()` 自动定位 —— 优先 `CLAUDE_PROJECT_DIR` 环境变量，回退 `git rev-parse --show-toplevel`。仓库外执行报错。

**新项目首次使用**：跑一次 `scripts/bootstrap_project.py` 自动建好骨架。详见下面「触发模式 / `/control init`」。

---

## 🔒 `/control status` 输出契约（硬规则）

> 这是为了消除"AI 看到脚本输出后自由排版"的问题。**所有 status 类查询的最终呈现以脚本输出为准。**

触发条件（任一）：

- `/control list`
- `/control status`
- `/control <key> status`
- 用户用同义说法询问任务列表 / 进度 / 现在做到哪儿了 / 给我一个总控任务表

执行步骤：

1. 调用 `render_control_status.py`（带或不带关键词，按触发模式）
2. **逐字复述**脚本 stdout 输出，包含但不限于：
   - 块头（`# 总控状态` / `# 活跃总控`）
   - 派生总体状态行
   - 任务统计行
   - 顶部附注行（如有）
   - 完整子任务总表（所有列：编号 / 子任务 / 状态 / 依赖 / 预期输出）
3. **禁止**：重排版、合并行、省略列、改列名、调整列顺序、给数据加省略号、把表格转成 bullet list、跨多任务时只输出部分
4. **允许**：表格之后追加**最多一段**简短"下一步建议"，格式必须从下列固定模板选一条：
   - 「下一步可执行：`Tn`（依赖已满足）」—— 存在可执行子任务
   - 「全部完成，可调用 `archive_control.py --apply` 归档」—— 派生状态 = 已完成
   - 「存在阻塞：`Tn`，请用户拍板」—— 派生状态 = 阻塞
   - 「未启动，请用户决定从哪个子任务开始」—— 派生状态 = 未启动
5. 用户没有问下一步时，第 4 步可以省略；不主动追加其他解读

错误处理：脚本报错（找不到总控 / 多候选 / 缺列）→ 把脚本的错误原文展示给用户，再询问应该怎么处理；不要"修复式 freestyle"。

---

## 触发模式

| 模式 | 作用 |
|------|------|
| `/control init` | **新项目首次使用**：建 docs/00-任务总控/ 骨架、追加 .gitignore（幂等） |
| `/control list` | 列出所有活跃总控（最少上下文） |
| `/control status` | 只读查看当前总控状态表 |
| `/control <关键词>` | 进入指定总控，列出可执行子任务，等用户选 |
| `/control <关键词> Tn` | 执行指定子任务（严格边界，支持 `Tn.x` 二级子任务） |
| `/control <关键词> status` | 查看指定总控状态 |
| `/control <关键词> split Tn` | 把一级父任务 Tn 拆为二级子任务 Tn.1 ~ Tn.N（用户必须先和 AI 对齐边界） |
| `/control blocked` | 列出所有阻塞子任务 |
| `/control switch` | 列出所有活跃总控，**交互式**让用户选一个写入激活指针 |
| `/control use <关键词>` | 直接按关键词设置激活总控（已知目标时用，比 switch 快） |
| `/control use --clear` | 清除激活配置 |
| `/control use --show` | 显示当前激活配置 |

**关键词省略时的目标选择优先级**：

1. 显式 `<关键词>`（用户传了就用这个）
2. `.claude/local/active-control` 文件指向的任务（多激活时显式指定）
3. 唯一兜底：只有 1 个未归档总控时直接选中
4. 否则报错列候选，要求加关键词或运行 `/control use <key>`

多候选时停止并让用户选择。

---

## 强制阅读（按粒度递增，最小化原则）

> **核心原则**：触发的命令越具体，读的文件越精准。**不要预先读所有文件**。

| 触发模式 | 必读文件 | 不读 |
|---------|---------|------|
| `/control init` | 无（直接调脚本） | — |
| `/control list` | `<PROJECT_ROOT>/docs/00-任务总控/README.md` | references/总控规范 / 各总控正文 |
| `/control <key>` 或 `/control <key> status` | 上 + 目标主总控 README.md 的「任务背景」「子任务总表」 | 子任务详情段、其他子任务、references |
| `/control <key> Tn` 或 `/control <key> Tn.x` | 上 + **该子任务详情** + 它列出的「强制阅读」文件 | 其他子任务详情、references |
| `/control <key> split Tn` | 上 + **Tn 父任务详情**（用于和用户对齐拆分边界） | 其他子任务详情 |
| 创建新总控 | `references/总控规范.md` + `task-control-doc` skill | — |
| 归档任务 | `references/总控规范.md` §2.3 + 归档目录索引 | — |

`CLAUDE.md` 由会话级注入，不需要再读。

---

## 自动化脚本

| 脚本 | 对应触发模式 |
|------|------------|
| `scripts/bootstrap_project.py` | `/control init` |
| `scripts/render_control_status.py --list` | `/control list` |
| `scripts/render_control_status.py [关键词]` | `/control [关键词] status` |
| `scripts/next_subtask.py [关键词]` | `/control [关键词]`（含完整会话启动提示词） |
| `scripts/next_subtask.py [关键词] --show Tn` | `/control [关键词] Tn` —— dump 子任务详情段（支持 `Tn.x`） |
| `scripts/split_subtask.py <关键词> Tn --subtasks "Tn.1=名1,..." [--apply]` | `/control [关键词] split Tn` —— 拆分（默认 dry-run） |
| `scripts/list_blocked.py` | `/control blocked` |
| `scripts/render_control_status.py --list` → 用户选择 → `scripts/set_active.py <精确名>` | `/control switch` |
| `scripts/set_active.py <关键词>` / `--clear` / `--show` | `/control use ...` |
| `scripts/archive_control.py <关键词> --version V1 [--apply]` | 归档（默认 dry-run） |

```bash
SKILL_DIR=~/.claude/skills/control/scripts

# 新项目首次初始化（幂等）
python3 $SKILL_DIR/bootstrap_project.py

# 最少上下文：只列活跃总控
python3 $SKILL_DIR/render_control_status.py --list

# 列指定总控的子任务概览
python3 $SKILL_DIR/render_control_status.py <关键词>

# 推荐下一个可执行子任务（输出含完整会话启动提示词，可复制即用）
python3 $SKILL_DIR/next_subtask.py <关键词>

# Dump 指定子任务详情段全文（用户已知做哪个，直接看完整工作包）
python3 $SKILL_DIR/next_subtask.py <关键词> --show T3

# 阻塞盘点
python3 $SKILL_DIR/list_blocked.py

# 交互式切换激活总控（/control switch）
# 步骤：① 列出所有活跃总控 ② 向用户展示编号列表 ③ 用户选择 ④ 写入指针
python3 $SKILL_DIR/render_control_status.py --list   # ① 获取候选列表
# → AI 把列表以编号形式呈现给用户，等待选择
# → 用户选定后执行：
python3 $SKILL_DIR/set_active.py <用户选中的精确目录名>  # ④ 写入指针

# 直接按关键词设置激活总控（/control use，已知目标时用）
python3 $SKILL_DIR/set_active.py <关键词>
python3 $SKILL_DIR/set_active.py --show
python3 $SKILL_DIR/set_active.py --clear

# 归档（默认 dry-run）
python3 $SKILL_DIR/archive_control.py <关键词> --version V1 --apply

# 拆分父任务（默认 dry-run，--apply 才写盘）
python3 $SKILL_DIR/split_subtask.py <关键词> Tn \
    --subtasks "Tn.1=表设计,Tn.2=接口契约,Tn.3=Migration" \
    --reason "Tn 工作量超出预期" --apply
```

---

## 执行流程

### 0. `/control switch` — 交互式切换激活指针

1. 运行 `render_control_status.py --list` 获取所有活跃总控
2. 若无活跃总控 → 提示先创建，停止
3. 若只有一个 → 直接写入，告知用户（无需选择）
4. 若有多个 → 以编号列表形式展示给用户（`1. xxx  2. yyy`），**等待用户回复编号或关键词**
5. 用户选定后运行 `set_active.py <精确目录名>` 写入 `.claude/local/active-control`
6. 输出确认：「已将激活总控切换为：xxx」

> **不读任何总控文档正文**，只需 `--list` 输出即可完成全流程。

---

### 1. 进入

1. 解析触发模式 → 确定需要的最小上下文（见上面的「强制阅读」表）
2. 用脚本获取索引信息（`render_control_status.py` 或 `next_subtask.py`）
3. 多候选时停止 → 列出候选，让用户选择
4. **不要自己解析总控文档**——脚本已经处理了
5. worktree 不绑定任务——任意 worktree 都可以切换激活总控。多激活时通过 `.claude/local/active-control` 文件确定默认目标，配置不存在且唯一总控时自动兜底

### 2. 子任务选择

用户没指定 Tn 时的优先级（已固化在 `next_subtask.py`）：

1. 状态为 `进行中` 的子任务（恢复未完成工作）
2. 第一个 `待完成` 且依赖均已 `已完成` 的子任务

不跳过未解决的依赖。全部阻塞 → 报告原因并停止。

### 3. 执行（严格边界）

**开始前**：
- 子任务状态改为 `进行中`
- 重新从磁盘读取该子任务详情和「强制阅读」文件——**不依赖聊天历史**
- 不读其他子任务详情
- 由用户在新会话开头自行选择模型（不在总控里预定义）

**执行中**：
- 改动严格限于「要做的事情」描述的范围
- 遵守「不做什么」字段（如有）
- 子任务详情有「会话启动提示词」时按它走
- 遵守项目本地的真值优先级与同步规则（项目自身的 CLAUDE.md / AGENTS.md）

**完成后**：
- **立刻停止**，不要继续做下一个子任务
- 回填总控（见下面的「回填」段）
- 向用户报告完成情况，等下一步指令

### 4. 回填

子任务完成后更新：

- 子任务总表「状态」 → `已完成`
- 子任务详情「当前状态」 → `已完成`
- 子任务详情「输出物」 → 实际产出文件列表
- 子任务详情「风险与注意事项」 → 新发现的残余风险（如有）
- 总控的「进展记录」追加一行：`- YYYY-MM-DD：[子任务编号] 完成，[简要摘要]`

阻塞时设为 `阻塞`，写明：阻塞什么、为何阻塞、最佳下一步。

### 5. 派给外部 agent 时

主流路径：用户在新会话执行子任务时，直接复制子任务详情末尾的「**会话启动提示词**」（或 `next_subtask.py` 输出末尾生成好的版本）。

如需主线程内 spawn agent（少数场景），prompt 必须注入边界声明（见 `references/总控规范.md` §4.3）：禁止接管任务调度、只做指定编号子任务。

### 5.5 `/control <key> split Tn` —— 中途拆分父任务

> 触发场景：用户在执行过程中发现某个一级任务 Tn 太大、单一会话做不完，需要原地拆为 Tn.1 ~ Tn.N 二级子任务继续推进。

**核心约束**：

- 只允许两级层次。`Tn.x` 不能再拆，深层拆要么开新总控、要么改设计
- **AI 不可自行决定拆分粒度** —— 必须先与用户对齐：拆几个、各自做什么、依赖顺序
- 用户对齐后才调脚本生成骨架，脚本写完只是占位，子任务详情仍由用户/AI 后续填写

**执行流程**：

1. 用户敲 `/control <key> split Tn`，或用自然语言"把 T3 拆一下"
2. AI 读取 Tn 父任务详情（用 `next_subtask.py --show Tn`），向用户呈现当前状态
3. AI **询问**用户：要拆为几个子任务、每个子任务负责什么、命名建议是什么
4. 用户答复后，AI **重复一次拆分计划**让用户确认（"拆 T3 为：T3.1=表设计、T3.2=接口契约、T3.3=Migration，理由：T3 工作量超出预期 —— 确认吗？"）
5. 用户确认后调脚本（默认 dry-run，预览改动）：
   ```bash
   python3 $SKILL_DIR/split_subtask.py <key> Tn \
       --subtasks "Tn.1=...,Tn.2=...,..." \
       --reason "..."
   ```
6. dry-run 输出无异常 → 加 `--apply` 真正写盘
7. AI 简要报告改动：父任务状态自动派生、子任务骨架已生成、提示用户后续要补全各子任务详情
8. **不要顺手开始执行任何子任务** —— 拆分完毕，等用户决定下一步

**拆分后的数据语义**：

- 父任务 Tn 在总表状态列写 `派生`，渲染时由脚本聚合子任务实际状态显示
- 原来对 Tn 的依赖（如 T(n+1) 依赖 Tn）保持不变，语义自动变为"所有 Tn.* 完成"
- 父任务**不会**再被 `next_subtask.py` 推荐执行；只有叶子节点可执行
- 归档校验只看叶子状态；派生父跳过

**拒绝场景**（脚本会自动报错）：

- 拆已完成 / 已取消的任务
- 拆子任务（Tn.x 不可再拆）
- 拆已经被拆过的父任务（不允许"追加"，要追加请手动改总表）
- 子任务清单少于 2 个 / 编号不从 .1 起 / 编号不连续

---

### 6. 收尾与归档

任务整体完成时（不是子任务完成时） → 用户确认后调脚本：

```bash
python3 ~/.claude/skills/control/scripts/archive_control.py <关键词> --version V1 --apply
```

脚本自动同步索引并迁移目录到 `归档/V{x}/`。归档前会校验所有子任务必须为 `已完成` 或 `已取消`。

如该任务有专属 worktree，归档完后手动 `git worktree remove`。

任务被明确删除/放弃 → 见 `references/总控规范.md` §2.4（手动操作，不进归档）。

---

## 回复用户

摘要应包含：

- 目标总控文档 + 子任务编号
- worktree 状态（如适用）
- **改了什么 / 没改什么**（突出边界遵守）
- 残余风险（如有）
- 建议下一步（**不要主动接着做**）
