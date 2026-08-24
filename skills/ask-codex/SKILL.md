---
name: ask-codex
description: 仅手动触发。用户明确要求“问一下 codex/GPT-5.5”或“让 codex 直接执行”时，通过一次性 codex exec 提供第二意见、审查或授权内施工。已完工代码的规格符合性核验改用 codex-review。
disable-model-invocation: true
---

# codex 咨询 / 派任务（ask-codex）

通过 `codex exec` 一次性非交互命令，让 GPT-5.5 承担第二意见、审查、或直接执行任务。

**设计哲学**：人保留分工权和最终决策权。AI 不做自动路由——用户不说触发词，主线程自己处理。用户说触发词，主线程严格按触发词对应模式执行。

**与「派 Claude 子代理」的根本差异**：用 `Agent` 工具起的 Claude 子代理，子代理是可持续对话的进程，派模式能"先探索汇报计划、等确认再动手"。codex 不是子代理，是一条一次性非交互命令行——**跑完即结束，没有"跑到一半停下来等确认"这回事**。因此本 skill 的派模式是**一次性直接执行**（任务+护栏一次性打包，执行完由主线程做事后 `git diff` 验收），不是"探索计划→确认→继续"的两阶段模式。

---

## 0. 与 codex-review / adversarial-review 的边界（进入本 skill 前必查）

codex 在这套技能体系里有三个入口，互不替代：

| Skill | 时机 | 前提 | 输出形态 |
|---|---|---|---|
| `adversarial-review` | 开工前，方案/高风险代码待定 | 无固定前提 | 双评审 + Opus 裁判报告 |
| `codex-review` | 施工完成后 | 必须有已冻结蓝图 + 决策表（或蓝图退化基线） | 强制 A/B/C 三级分类 + 证据闸 + 分流台账 |
| **本 skill（ask-codex）** | 任意时刻 | 无前提，随问随答 | 自由文本结论 / 直接执行 |

**强制检查（触发本 skill 前）**：问题是不是"核验代码是否照已冻结的蓝图/决策表施工"？

- **命中** → 停止，改用 `codex-review`。它的证据闸和三级分流协议专门防止"把已拍板决策误判成 bug、又被照改"，本 skill 没有这套保护，绕开它会架空那套纪律。
- **没命中**（轻量咨询、非代码问题、没有冻结真值可核对、或直接派任务执行）→ 才用本 skill。

方案/高风险代码的开工前评审同理指向 `adversarial-review`，不进本 skill。

---

## 1. 模型映射

| 模式 | 触发词 | codex 参数 |
|---|---|---|
| **问 codex**（默认） | 问一下codex、问一下gpt、问一下gpt5.5 | `-m gpt-5.5`，reasoning 默认 xhigh（config 默认即是，无需显式传） |
| **派 codex** | 让codex去做XX、让codex直接XX、让gpt去做XX、让gpt直接XX | 同上 |

- 用户未指定降级时，默认 xhigh（超强思考）
- 用户说"快速 / 省着点跑" → 降级 `-c 'model_reasoning_effort="medium"'`
- 用户不说触发词 → 不调 codex，主线程自己处理
- 触发词模糊时 → 直接问用户："你想问模式还是派模式？"

成本提示：xhigh 质量最高也最慢（常 60–180s，复杂任务更久），调用必须走后台（§5）。

---

## 2. 模式路由

```
用户消息
  │
  ├─ 不含触发词 → 主线程直接处理
  │
  └─ 含触发词
        │
        ├─ 先过 §0 边界检查 → 命中 codex-review / adversarial-review 范围 → 转对应 skill，不进本 skill
        │
        └─ 未命中
              │
              ├─ "问一下" / "怎么看" / "审查" / "评审"
              │   → 问模式（§3）
              │
              └─ "让XX去做" / "让XX直接" / "派XX"
                  → 派模式（§4）
```

---

## 3. 问模式

**用途**：让 codex 回答一个问题（设计审查、技术分析、方案评估、代码片段审查等）。codex 只读不改，输出结论到文件，主线程消化后回答用户。

**沙箱**：`-s read-only`（物理上写不了任何东西）。

### 3.1 打包指南

方法论复用 §8 引用的证据包制作规范（RAM 框架：R 谁读 / A 干什么 / M 最小充分集）。槽位：

```
[具体问题] — 一句话，可被独立回答，不依赖隐含上下文

[文件引用] — 需要读的代码/文档文件，精确到方法/行范围
  格式：文件路径（只读：方法名/行范围）
  必须附带禁入声明："只读以上列出的文件，不要自行查找其他文件"

[背景事实] — 回答此问题必须知道的关键事实（先浓缩再写入，不贴超过 5 行原始代码）

[约束条件] — 从 CLAUDE.md 摘出适用条款，内嵌原文，不写"参考 CLAUDE.md"

[判断标准] — 什么算好答案

[外部信息] — 非代码的参考信息（如有）
```

填槽原则与派 Claude 子代理时一致：先浓缩再装包、每项内容过 RAM 检验句、不确定就不装、不设数字上限。

### 3.2 Prompt 模板

```
[具体问题]

信息来源声明（必填）：
- 交付形式：只读分析，输出到指定文件，不改任何文件
- 已读文件白名单：
  - [文件路径]（读取范围：方法名 / 行号）
  - （代码题必填；非代码题若无文件引用可写"无文件引用"）
- 未纳入本包的已知信息：
  - [内容] — 原因：[为什么排除]

[文件引用 / 背景事实 / 约束条件 / 判断标准 / 外部信息]
（按需填入，无关槽位留空。每项内容必须能通过 RAM 检验句。）

输出要求：
- 把结论写入指定输出文件。不要改任何其他文件，不要创建其他文件。
- 如果现有信息不足以给出可靠结论，不要硬答。先声明缺失的关键信息，再给出基于明确假设的条件性结论。
  格式：⚠️ 信息不足：缺少 [X]。以下结论基于假设 [Y]。
```

### 3.3 调用命令（codex exec，问模式）

```bash
# 派生本轮 scratch 目录（并发安全保险，同 adversarial-review §3.2 机制）
REPORT='<本轮输出文件路径，可用 scratch 内临时文件，也可用用户指定路径>'
case "$REPORT" in /*) ABS_OUT="$REPORT" ;; *) ABS_OUT="$PWD/$REPORT" ;; esac
PHASH=$(printf '%s' "$ABS_OUT" | shasum -a256 | cut -c1-12)
SCRATCH=$(mktemp -d "/tmp/ask-codex-${PHASH}-XXXXXX")
echo "ABS_OUT=$ABS_OUT"; echo "SCRATCH=$SCRATCH"   # 记住这两行字面值，后续 Bash 调用直接粘贴复用

# -C 工作目录选择：评审/咨询项目内代码 → 指向项目根/对应 worktree；与项目无关的问题 → /tmp
CODEX_CWD="$(git rev-parse --show-toplevel 2>/dev/null || echo /tmp)"

cat > "$SCRATCH/ask-prompt.txt" << 'PROMPT_EOF'
[§3.2 制好的 prompt]
PROMPT_EOF

codex exec \
  -m gpt-5.5 \
  -c 'approval_policy="never"' \
  -s read-only \
  -C "$CODEX_CWD" \
  --skip-git-repo-check \
  --ephemeral \
  -o "$ABS_OUT" \
  "$(cat "$SCRATCH/ask-prompt.txt")" \
  < /dev/null \
  > "$SCRATCH/ask-log.txt" 2>&1
```

- 用 Bash 工具 `run_in_background: true` 发起（可能超 10 分钟，前台 Bash 上限容不下）。
- 降级：加 `-c 'model_reasoning_effort="medium"'`。
- 进程退出后再起一次 Bash，粘贴本轮记住的 `$ABS_OUT` 字面值，`cat "$ABS_OUT"` 读取结论；日志在 `$SCRATCH/ask-log.txt`。

---

## 4. 派模式

**用途**：让 codex 在授权范围内**一次性直接执行**任务（含新建文件）。codex 自己判断需要改哪些文件；执行完成后由主线程做事后 `git diff` 验收——**不做执行中途的计划确认**（§0 已说明原因：codex exec 是一次性命令，无法"跑到一半停下来等确认"）。

**沙箱**：`-s workspace-write`（`-C` 指定的目录即为可写工作区）。

**核心原则**：主线程给"意图 + 护栏"，一次性打包完整上下文，codex 决定执行路径。护栏必须比问模式更详尽——没有中途纠偏机会，前置约束就是唯一的安全网。

### 4.1 Prompt 模板

```
[任务描述] — 要做什么
[验收标准] — 做到什么程度算完成

▸ 禁止区（绝对不能碰的文件/目录/模块）
  - [明确排除的范围]

▸ 约束（必须遵守的规则，从 CLAUDE.md 内嵌原文）
  - [适用条款]

▸ 执行要求
  自主探索代码、确定需要改动/新建哪些文件，直接执行，不要中途汇报计划等待确认。
  完成后在输出文件里给出改动摘要：
  
  ## 改动摘要
  已修改：
    - [文件路径]：改了什么
  已新建：
    - [文件路径]：做什么用
  未完成 / 遇到的阻塞：
    - [说明]（如有）
  自评是否达到验收标准：[是/否 + 理由]
```

### 4.2 调用命令（codex exec，派模式）

```bash
REPORT='<本轮改动摘要输出文件路径>'
case "$REPORT" in /*) ABS_OUT="$REPORT" ;; *) ABS_OUT="$PWD/$REPORT" ;; esac
PHASH=$(printf '%s' "$ABS_OUT" | shasum -a256 | cut -c1-12)
SCRATCH=$(mktemp -d "/tmp/ask-codex-${PHASH}-XXXXXX")
echo "ABS_OUT=$ABS_OUT"; echo "SCRATCH=$SCRATCH"

# -C 必须指向要改动的项目根/对应 worktree（workspace-write 沙箱里唯一可写目录就是这里）
CODEX_CWD="$(git rev-parse --show-toplevel 2>/dev/null || echo /tmp)"

cat > "$SCRATCH/ask-prompt.txt" << 'PROMPT_EOF'
[§4.1 制好的 prompt]
PROMPT_EOF

codex exec \
  -m gpt-5.5 \
  -c 'approval_policy="never"' \
  -s workspace-write \
  -C "$CODEX_CWD" \
  --skip-git-repo-check \
  --ephemeral \
  -o "$ABS_OUT" \
  "$(cat "$SCRATCH/ask-prompt.txt")" \
  < /dev/null \
  > "$SCRATCH/ask-log.txt" 2>&1
```

- 用 Bash 工具 `run_in_background: true` 发起。
- `workspace-write` 沙箱默认**不开网络访问**（不能装依赖、不能拉远程资源）；如任务确实需要网络（如需联网的 `mvn`/`npm` 安装），显式加 `-c sandbox_workspace_write.network_access=true`，并在向用户报告时说明已放开网络访问。
- 降级：加 `-c 'model_reasoning_effort="medium"'`。
- 进程退出后再起一次 Bash，`cat "$ABS_OUT"` 读取改动摘要；日志在 `$SCRATCH/ask-log.txt`。

### 4.3 隔离（可选）

如任务改动面大、想要文件隔离，先用 `git-worktree` skill 建好独立 worktree，再把上面命令里的 `CODEX_CWD` 手动指向该 worktree 路径。本 skill 不内置自动 worktree 派生（codex exec 没有类似 Agent `isolation` 参数的内建机制）。

### 4.4 主线程验收清单

```
□ 输出文件 "$ABS_OUT" 存在且非空（mtime 在本轮之后）
□ 范围检查：git status --porcelain / git diff --name-only，改动是否都在授权范围内？
□ 编译检查：改动是否引入编译错误？
□ 约束检查：每条约束都遵守了吗？
□ 验收标准：每一项都完成了吗？
□ 越界检查：有没有改动禁止区文件？有 → 撤销超出部分，告知用户
```

全部通过 → 向用户报告改动摘要。不通过 → 主线程修正，或告知用户具体问题。

---

## 5. 调用机制说明

- **后台执行**：codex exec 用 Bash 工具 `run_in_background: true` 发起，不用前台等待（前台 Bash 上限只有 10 分钟，容不下慢速评审）。
- **scratch 隔离**：`mktemp -d` 派生本轮专属临时目录，防止多任务并发时 prompt/日志互相覆盖；机制与 `adversarial-review` §3.2 相同。
- **stdin 必须重定向 `< /dev/null`**，否则 codex 检测到 stdin 是管道会永久阻塞。
- **`-C` 工作目录选择**：涉及项目内容 → 项目根/对应 worktree；与项目无关的独立问题 → `/tmp`。判别标准同 `adversarial-review` §7.2："项目根 CLAUDE.md/AGENTS.md 是工程规约 → 进项目；是人格/身份设定 → 隔离到 /tmp"。
- **禁止** `--dangerously-bypass-approvals-and-sandbox`——问模式无理由绕过只读沙箱；派模式的写权限已经由 `-s workspace-write` 显式声明，不需要也不允许全开权限。
- codex exec 没有 system/user 分离，角色设定合并进 prompt 首部即可。

---

## 6. 异常处理

| 异常 | 处理 |
|---|---|
| codex 不可用 / 配额耗尽 | 告知用户："codex 不可用，是否需要降级为主线程自己处理？" |
| 调用超时（>30min）/ 失败 | 重试一次；仍失败 → 报告用户，不伪造结论 |
| 输出为空 | 检查 prompt 是否有歧义或信息缺口，修正后重试；仍空 → 报告用户 |
| 输出被截断 | prompt 末尾加"如输出过长，优先输出结论/改动摘要部分" |
| 派模式：codex 改动超出授权范围 | 按 §4.4 撤销超出部分的改动，告知用户 |
| 派模式：codex 未完成任务但已产生部分改动 | 主线程判断回滚还是补完，报告用户裁决，不擅自决定 |
| 派模式：workspace-write 因需要网络被卡住 | 检查是否需要 `sandbox_workspace_write.network_access=true`（见 §4.2），重试前告知用户将放开网络访问 |

---

## 7. 主线程职责

### 7.1 问模式

- 消化 codex 结论，用自己的话告诉用户，附加独立判断
- 不要把 codex 输出当作最终答案——你是决策者，codex 是顾问
- 如果 codex 答案有矛盾或涉嫌事实错误，明确提醒用户
- codex 输出"⚠️ 信息不足"声明时，必须向用户说明基于什么假设得出结论

### 7.2 派模式

- 按 §4.4 验收 codex 的改动
- 向用户报告：改了什么、发现了什么问题、做了什么修正

### 7.3 成本意识

- 信息收集（读文件、搜索、整理）→ 主线程自己做，不调 codex
- 深度推理、代码生成、方案判断、第二意见 → 调 codex
- 简单问答（查一下、找一下）→ 主线程直接回复，不调 codex

### 7.4 禁止

- 不要在问模式下让 codex 改文件
- 不要在派模式下让 codex 超出授权范围而不做事后验收
- 不要用一次 codex exec 反复追问（每次追问开新调用）
- 用户没触发就不要调
- 命中 §0 边界检查范围时不要用本 skill 硬顶上——转对应 skill

---

## 8. 参考文档

本 skill 的证据包方法论**复用** `adversarial-review` skill 的 `references/证据包制作规范.md`（RAM 框架：R 谁读 / A 干什么 / M 最小充分集，三种交付方式，约束区内嵌原文）——单一真值源，不在本 skill 内重复维护一份。

- 日常场景：直接用本 skill §3/§4 的内联模板
- 复杂场景（多文件、多层约束、待决策点）：先读该文档深度制包，再通过本 skill 调用
