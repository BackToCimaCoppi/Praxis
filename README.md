# Praxis

> 一套给「AI 驱动开发」立规矩的 Claude Code skill 方法论库。
> 让 AI 写代码又快又不失控——文档不漂移、评审不走过场、大任务不越界、施工范围不失控。

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
![Docs](https://img.shields.io/badge/docs-简体中文-red.svg)
![Skills](https://img.shields.io/badge/skills-15-green.svg)

---

## 这是什么

Praxis 是一组可直接装进 [Claude Code](https://claude.com/claude-code) 的 **skill**（技能）。
每个 skill 是一份 AI 自动加载、照着执行的工作流规范。它们覆盖 AI 辅助开发的全链路：
反推文档、分层治理、设计、施工、评审、任务编排、Git 流程。

**为什么需要它？** AI 写代码很快，但默认状态下也很「野」：

- 改了代码不同步文档 → 文档和现实**漂移**，越攒越不可信
- 让 AI「评审一下」→ 它既当运动员又当裁判，**走过场**
- 丢一个大任务给 AI → 它**越界**乱改、上下文一满就失忆
- 不画图纸直接写 → **施工范围失控**，改一处崩一片

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

## ⭐ 维护者私心力荐

如果你只想先试一个组合，从这两个开始——它们是「大任务不失控」的命门，也是我自己用得最多的搭配：

- **[task-control-doc](docs/task-control-doc.md)** —— 先把一个跨多次会话的大任务，拆成一个个**自包含工作包**（图纸）。
- **[control](docs/control.md)** —— 再让 AI 照图纸**严格逐格施工**：一次只动一个子任务，做完即停、绝不越界。

「先拆图纸、再按格施工」——AI 上下文再满也不会失忆，范围再大也不会跑偏。

> 招牌（最能代表项目的）是 [doc-layer-system](docs/doc-layer-system.md)；这两个是维护者私心最爱。

## 安装

把 `skills/` 下你需要的目录拷进 Claude Code 的 skill 目录：

```bash
# 全部安装
cp -R skills/* ~/.claude/skills/

# 或只装你要的
cp -R skills/adversarial-review ~/.claude/skills/
```

> 同级目录很重要：部分 skill 之间有引用（如 `adversarial-review` 复用 `ask-opus` 的方法论），
> 安装时保持它们在 `~/.claude/skills/` 下平级即可。

**依赖**：多数 skill 仅用 Claude Code 内置能力。`adversarial-review` 的 GPT 评审一侧需要
[codex CLI](https://github.com/openai/codex)；没有 codex 时它会自动降级为单侧评审。

## Skill 总表

点击 skill 名跳转到该 skill 的「手把手」详解文档。

### 📐 文档体系
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [doc-layer-system](docs/doc-layer-system.md) | 七层文档体系引擎（招牌） | 想给项目建立"代码与文档不脱节"的分层治理体系 |
| [docs-from-code](docs/docs-from-code.md) | 从代码反推 L1 需求文档 | 老项目没需求文档，要从现有代码补回来 |
| [long-doc-governance](docs/long-doc-governance.md) | 长文档拆分治理 | 单个文档越写越长、该拆了 |

### 🔍 冷启动 / 反推
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [code-to-7layer](docs/code-to-7layer.md) | 从代码反推七层文档骨架总控 | 接手一个没文档的项目，想系统性补全文档体系 |
| [code-to-guide](docs/code-to-guide.md) | 从代码生成 AI 友好项目导览 | 想让 AI（或新人）快速摸清一个陌生代码库 |

### ✏️ 设计 / 施工
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [lightweight-design](docs/lightweight-design.md) | 单次局部修改的任务级设计 | 改一个小功能，先把"改什么、怎么改"锁死 |
| [construction-blueprint](docs/construction-blueprint.md) | 写代码前的施工蓝图 | 动手前先出"逐文件变更图纸"，限制施工范围 |

### ⚖️ 评审
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [adversarial-review](docs/adversarial-review.md) | Claude×GPT 双独立评审 + 裁判 | 重要方案/代码定稿前，要一份经得起挑战的评审 |

### 🧭 任务编排
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [task-control-doc](docs/task-control-doc.md) | 大任务总控文档方法论 ⭐ 维护者私心力荐 | 一个跨多次会话的大任务，要先拆成自包含工作包 |
| [control](docs/control.md) | 总控执行引擎（严格单子任务）⭐ 维护者私心力荐 | 照着总控文档逐个子任务推进，做完即停、不越界 |

### 📨 派活问询
| Skill | 一句话 | 用在什么场景 |
|-------|--------|------------|
| [ask-claude](docs/ask-claude.md) | 派活给 Claude（按需选档） | 把一个子问题打包派给另一个 Claude 线程 |
| [ask-opus](docs/ask-opus.md) | 派活给 Opus（高规格档） | 难题需要最强模型独立思考 |
| [ask-sonnet](docs/ask-sonnet.md) | 派活给 Sonnet（快省档） | 常规子任务，要快要省 |

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
