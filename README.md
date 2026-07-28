# Praxis

> 一套给「AI 驱动开发」立规矩的 Claude Code skill 方法论库。
> 让 AI 写代码又快又不失控——文档不漂移、评审不走过场、大任务不越界、施工范围不失控。

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
![Docs](https://img.shields.io/badge/docs-简体中文-red.svg)
![Skills](https://img.shields.io/badge/skills-23-green.svg)

---

## 这是什么

Praxis 是一组可直接装进 [Claude Code](https://claude.com/claude-code) 的 **skill**（技能）。
每个 skill 是一份 AI 自动加载、照着执行的工作流规范。它们覆盖 AI 辅助开发的全链路：
反推文档、分层治理、设计、施工、测试、评审、自主执行、任务编排、Git 流程。

**为什么需要它？** AI 写代码很快，但默认状态下也很「野」：

- 改了代码不同步文档 → 文档和现实**漂移**，越攒越不可信
- 让 AI「评审一下」→ 它既当运动员又当裁判，**走过场**；而认真评起来又停不下，一轮加一轮**没完没了**
- 丢一个大任务给 AI → 它**越界**乱改、上下文一满就失忆
- 不画图纸直接写 → **施工范围失控**，改一处崩一片
- AI 自己写测试、自己判通过 → 跑不过就**把断言改松**，测试全绿而业务语义一个没验
- 让它一口气跑完长任务 → 要么每十分钟被打断，要么**跑飞了没人拦**

Praxis 把这些痛点逐个收成可执行的 skill——把「该有的纪律」固化进流程，而不是靠每次提醒。

## 核心理念：通用引擎 + 项目补丁

所有 skill 都是**项目无关的通用引擎**——只含方法论与规则，**不硬编码**任何具体项目的路径、
业务域、审查人。项目独有的值通过你自己的**项目级补丁**注入（见
[`templates/项目级补丁模板/`](templates/项目级补丁模板/SKILL.md)）。

```
Praxis 的 skill（通用引擎，留白挂载点）
        ↑ 挂载
你项目的补丁 skill（填上你的路径/域/死亡线/审查人）
```

这样同一套引擎能服务任何项目，而你的项目隐私永远留在你自己仓库里。

## 🐎 三驾马车（Core Trio）

整个库的脊梁是这三套，串起来就是 AI 驱动开发的「**规划 → 治理 → 把关**」闭环：

1. **总控** · [task-control-doc](docs/task-control-doc.md) + [control](docs/control.md) —— ⭐ **维护者最爱**
   先把跨多次会话的大任务拆成**自包含工作包**（图纸），再让 AI **严格逐格施工**：一次只动一个子任务、做完即停、绝不越界。AI 上下文再满不失忆、范围再大不跑偏。
2. **七层文档** · [doc-layer-system](docs/doc-layer-system.md) —— 项目招牌
   给代码与文档建立分层治理，让两者永不脱节；死亡线区域强制真人把关。
3. **对抗评审** · [adversarial-review](docs/adversarial-review.md)
   同一份方案，两个不同模型各出一份独立评审，主线程逐条裁决。**同一对象只开放一次**，整改转[封闭验收](docs/closed-remediation-review.md)——既防评审走过场，也防评审无限加码。

> 只想先试一个？从 **总控** 开始。

### 想让 AI 一口气把活干完？

如果你的目标不是"逐道工序审"，而是"**交出去、它自己跑到底、我只在起点和终点各出面一次**"，
那就是另一条链路——从规格冻结到自主执行的结果管控闭环：

```
lightweight-design  设计决策钉死
        ↓
test-standards → test-case-design   用例先于施工冻结（断言编号 + 哈希锚）
        ↓
goal-charter  写执行契约（目标 + 验证器 + 边界 + 自愈清单）→ 红队一次 → 用户拍板
        ↓
自主执行 ──→ test-execution-router  跑测试、收证据、失败分类
        ↓
候选终审（人只在这里再出现一次）
```

配套两道安全阀：[deep-research-gate](docs/deep-research-gate.md) 管住扇出别烧穿配额，
[codex-review](docs/codex-review.md) 提供事后的低成本符合性核验。

## 安装

把 `skills/` 下你需要的目录拷进 Claude Code 的 skill 目录：

```bash
# 全部安装
cp -R skills/* ~/.claude/skills/

# 或只装你要的
cp -R skills/adversarial-review ~/.claude/skills/
```

> 同级目录很重要：部分 skill 之间有引用（如评审整改验收会回落到对抗评审、测试执行会回落到测试规范），
> 安装时保持它们在 `~/.claude/skills/` 下平级即可。

**依赖**：多数 skill 仅用 Claude Code 内置能力。需要 [codex CLI](https://github.com/openai/codex) 的有三个：
`adversarial-review` 的第二评审席（没有 codex 时降级为单侧评审）、`codex-review` 与 `ask-codex`（没有 codex 则不可用）。

## Skill 总表

点击 skill 名跳转到该 skill 的「手把手」详解文档。

### 📐 文档体系
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [doc-layer-system](docs/doc-layer-system.md) | 七层文档体系引擎 🐎 三驾马车·招牌 | 想给项目建立"代码与文档不脱节"的分层治理体系 |
| [docs-from-code](docs/docs-from-code.md) | 从代码反推 L1 需求文档 | 老项目没需求文档，要从现有代码补回来 |
| [long-doc-governance](docs/long-doc-governance.md) | 长文档拆分治理 | 单个文档越写越长、该拆了 |

### 🔍 冷启动 / 反推
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [code-to-7layer](docs/code-to-7layer.md) | 从代码反推七层文档骨架总控 | 接手一个没文档的项目，想系统性补全文档体系 |
| [code-to-guide](docs/code-to-guide.md) | 从代码生成 AI 友好项目导览 | 想让 AI（或新人）快速摸清一个陌生代码库 |
| [legacy-archaeology](docs/legacy-archaeology.md) | 老代码反推「业务/库/接口」三层下钻知识库 | 重构老系统前，要把黑盒老项目翻译成给 AI 注入背景的知识库 |

### ✏️ 设计 / 施工
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [lightweight-design](docs/lightweight-design.md) | 单次局部修改的任务级设计 | 改一个小功能，先把"改什么、怎么改"锁死 |
| [construction-blueprint](docs/construction-blueprint.md) | 写代码前的施工蓝图 | 动手前先出"逐文件变更图纸"，限制施工范围 |

### 🎯 自主执行
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [goal-charter](docs/goal-charter.md) | 写自主执行契约（目标+验证器+边界+自愈清单） | 要它一口气跑完，人只在起点拍板、终点验收 |
| [deep-research-gate](docs/deep-research-gate.md) | 扇出安全门（有界并行放行，深度研究焊死） | 决定"要不要并行派一批子 agent / 开深度研究" |

### 🧪 测试
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [test-standards](docs/test-standards.md) | 测什么、测多深、什么不许交付 | 改动完成后，先定出本次的测试矩阵与质量闸 |
| [test-case-design](docs/test-case-design.md) | 施工前冻结的用例规格（断言编号+哈希锚） | 要让"改断言让测试变绿"这条路彻底走不通 |
| [test-execution-router](docs/test-execution-router.md) | 冻结用例 → 执行、证据、失败分类 | 把用例落成脚本跑起来，并对账收口 |

### ⚖️ 评审
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [adversarial-review](docs/adversarial-review.md) | 双模型独立评审 + 主线程裁决 🐎 三驾马车 | 重要方案/代码定稿前，要一份经得起挑战的评审 |
| [closed-remediation-review](docs/closed-remediation-review.md) | 整改验收（清单冻结，不许扩张） | 评审意见回补完，核验有没有落实、有没有夹带 |
| [codex-review](docs/codex-review.md) | 单模型低成本符合性核验 | 施工完成后，查实现有没有偏离已冻结的规格 |

### 🎨 呈现 / 可视化
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [design-preview](docs/design-preview.md) | UI 形态还原成像素级 HTML 并弹浏览器 | 聊页面版式时，让人对着真图评审而不是看文字 |
| [doc-html-style](docs/doc-html-style.md) | 桌面优先、色彩克制而丰富的文档 HTML | 把文档写成给人在电脑上读的 HTML 成品 |

### 📨 派活问询
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [ask-codex](docs/ask-codex.md) | 一次性调外部模型问问题或派任务 | 要个第二意见，或直接让它执行一段活 |

### 🧭 任务编排
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [task-control-doc](docs/task-control-doc.md) | 大任务总控文档方法论 🐎 三驾马车 · ⭐ 维护者最爱 | 一个跨多次会话的大任务，要先拆成自包含工作包 |
| [control](docs/control.md) | 总控执行引擎（严格单子任务）🐎 三驾马车 · ⭐ 维护者最爱 | 照着总控文档逐个子任务推进，做完即停、不越界 |

### 🔧 Git 流程
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [commit-changes](docs/commit-changes.md) | 受控提交流程 | 想要"看 diff、逐文件确认、规范信息"的安全提交 |
| [git-worktree](docs/git-worktree.md) | 多 worktree 生命周期管理 | 多分支并行开发，要管 worktree 的建/合/同步/清 |

## 贡献

欢迎补充新 skill。为保持全库格式统一（skill 结构、文档四段式、脱敏纪律），
请先读 [CONTRIBUTING.md](CONTRIBUTING.md)（规范真值源在 [CLAUDE.md](CLAUDE.md)）。

## 协议

[Apache License 2.0](LICENSE)。随便用、随便改、可商用，保留版权与变更声明即可。
