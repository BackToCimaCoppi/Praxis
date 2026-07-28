---
name: git-worktree
description: Git worktree 生命周期管理 skill（用户级通用）。触发后弹出菜单，支持：新建 worktree、把当前 worktree 合并到主干、把主干同步到所有 worktree、清理当前 worktree。主干分支名与 worktree 命名前缀均运行时自动探测，不绑定具体项目。触发词：创建 worktree、新建 worktree、worktree 合并、合并到主干、主干同步、同步所有 worktree、清理 worktree、git worktree、worktree 管理。
allowed-tools: Bash, Read
---

# git-worktree

多 worktree 并行开发管理工具。主仓库当前 checkout 的分支即**主干分支**，是唯一主干，所有 worktree 的改动最终合并回主干。worktree 与任何总控/任务体系**解绑**——同一 worktree 可承载多个任务，若项目启用了 `control` skill，通过 `/control switch` 切换。

## 约定探测（所有操作的公共前置）

```bash
# 主仓库路径 = git worktree list 的第一行（git 保证主仓库永远排第一）
MAIN_ROOT=$(git worktree list | head -1 | awk '{print $1}')
# 主干分支 = 主仓库当前 checkout 的分支
TRUNK_BRANCH=$(git -C "$MAIN_ROOT" branch --show-current)
# worktree 目录命名前缀 = 主仓库目录名
REPO_NAME=$(basename "$MAIN_ROOT")
PARENT_DIR=$(dirname "$MAIN_ROOT")

# 布局探测：主仓库目录名 == 主干分支名（容器目录布局，如 ~/projects/myrepo/main）→ worktree 不带前缀
if [ "$REPO_NAME" = "$TRUNK_BRANCH" ]; then
    WT_PREFIX=""              # 容器布局：worktree 目录 = PARENT_DIR/{名称}
else
    WT_PREFIX="$REPO_NAME-"   # 传统布局：worktree 目录 = PARENT_DIR/{REPO_NAME}-{名称}
fi
```

> 若 `TRUNK_BRANCH` 探测为空（主仓库处于 detached HEAD），停下询问用户主干分支名，不猜测。

## 合并原则（所有涉及合并的操作均遵守）

1. 先提交**源分支**的未提交改动
2. 再提交**目标分支**的未提交改动
3. 执行 merge
4. 遇到冲突直接解决，不 stash、不建中间分支

---

## 触发入口（强制）

skill 被调用后，**第一步必须**用 `AskUserQuestion` 询问用户选择操作：

问题：**你想执行哪个 worktree 操作？**

选项：
- **新建 worktree**：从主干拉出新分支，在兄弟目录创建 worktree
- **合并到主干**：把当前 worktree commit 并 merge 到主干（完工时用）
- **主干同步到所有 worktree**：把主干 merge 进每个 feature worktree（重大改动时用）
- **清理当前 worktree**：验证已全部合并到主干后删除 worktree 和分支

根据用户选择跳到对应 §。

---

## §A. 新建 worktree

**输入**：向用户询问英文任务名（如 `poster-render`、`user-finetune`）

**命名规则**：
- 目录名：`{WT_PREFIX}{名称}`（传统布局为 `{REPO_NAME}-{名称}`，容器布局直接 `{名称}`，探测逻辑见「约定探测」）
- 路径：主仓库的**兄弟目录**（`PARENT_DIR/{WT_PREFIX}{名称}`）
- 分支：`feature/{名称}`，从最新主干拉出
- **禁止**放在主仓库任何子目录内（会污染 git status）

**执行命令**：

```bash
# 先跑「约定探测」得到 MAIN_ROOT / TRUNK_BRANCH / REPO_NAME / PARENT_DIR / WT_PREFIX
NAME="<用户提供>"

# 更新主干
git -C "$MAIN_ROOT" fetch origin "$TRUNK_BRANCH"

# 创建 worktree
git -C "$MAIN_ROOT" worktree add "$PARENT_DIR/$WT_PREFIX$NAME" -b "feature/$NAME" "$TRUNK_BRANCH"

# 验证
git -C "$MAIN_ROOT" worktree list
```

**完成后**：告知用户新 worktree 的完整路径和分支名。

---

## §B. 合并当前 worktree 到主干

**适用场景**：当前 worktree 完工，把改动 merge 到主干。不同步到其他 worktree（如需同步，之后再执行 §C）。

**执行步骤**：

```bash
CURRENT_BRANCH=$(git branch --show-current)
# 先跑「约定探测」得到 MAIN_ROOT / TRUNK_BRANCH

# Step 1：提交当前 worktree 的改动（若有）
git status --short
# 有改动则向用户确认 commit message 后执行：
git add .
git commit -m "<用户提供的 commit message>"

# Step 2：提交主干的改动（若有）
git -C "$MAIN_ROOT" status --short
# 有改动则向用户确认 commit message 后执行：
git -C "$MAIN_ROOT" add .
git -C "$MAIN_ROOT" commit -m "<用户提供的 commit message>"

# Step 3：merge 到主干
git -C "$MAIN_ROOT" merge "$CURRENT_BRANCH" --no-ff -m "Merge $CURRENT_BRANCH into $TRUNK_BRANCH"

# 如果有冲突：
# 1. 展示冲突文件列表
# 2. 协助用户逐个解决
# 3. git add <resolved files>
# 4. git commit

# Step 4：验证
git -C "$MAIN_ROOT" log --oneline -5
```

---

## §C. 主干同步到所有 worktree

**适用场景**：主干有重大改动（如共享依赖、接口变更），需要让所有 feature worktree 跟上。

**执行步骤**（对每个 feature worktree 依次处理）：

```bash
# 先跑「约定探测」得到 MAIN_ROOT / TRUNK_BRANCH

git -C "$MAIN_ROOT" worktree list --porcelain | grep "^worktree" | awk '{print $2}' | while read wt; do
    [ "$wt" = "$MAIN_ROOT" ] && continue   # 跳过主仓库（主干自身）
    WB=$(git -C "$wt" branch --show-current)
    echo "=== 处理 $wt ($WB) ==="

    # Step 1：提交该 worktree 的未提交改动（若有）
    if ! git -C "$wt" diff --quiet || ! git -C "$wt" diff --cached --quiet; then
        echo "  ↳ 有未提交改动，先提交..."
        git -C "$wt" add .
        git -C "$wt" commit -m "wip: commit before syncing $TRUNK_BRANCH"
    fi

    # Step 2：merge 主干
    git -C "$wt" merge "$TRUNK_BRANCH" --no-ff
    if [ $? -ne 0 ]; then
        echo "⚠️  $wt 有冲突，已暂停。请进入该目录解决冲突后再继续："
        echo "   cd $wt && git status"
        break   # 停下，等用户解决冲突后重新触发
    fi

    echo "  ✓ $wt 同步完成"
done
```

> [!IMPORTANT]
> 遇到冲突时停下，告知用户冲突 worktree 路径，等用户进入解决后重新触发同步。

---

## §D. 清理当前 worktree

**前置验证**（两项必须全部通过才继续删除）：

```bash
CURRENT_BRANCH=$(git branch --show-current)
# 先跑「约定探测」得到 MAIN_ROOT / TRUNK_BRANCH

# 验证1：有无未提交改动
git status --short

# 验证2：有无未合并到主干的 commit
git -C "$MAIN_ROOT" log "$TRUNK_BRANCH".."$CURRENT_BRANCH" --oneline
```

**处理逻辑**：
- 有未提交改动 → 先提交（向用户确认 message），再重新验证
- 有未合并 commit → 停止，提示用户先执行 §B 合并到主干
- 两项均干净 → 执行删除

**执行删除**：

```bash
WORKTREE_PATH=$(git rev-parse --show-toplevel)

git -C "$MAIN_ROOT" worktree remove "$WORKTREE_PATH"
git -C "$MAIN_ROOT" branch -d "$CURRENT_BRANCH"
git -C "$MAIN_ROOT" worktree list
```

> [!CAUTION]
> AI **不自动加 `--force`**。`git worktree remove` 报错时停下报告，由用户决定如何处理。

---

## 不在范围内

- 项目自身的任务/总控体系切换（若项目启用了 `control` skill，用 `/control switch` 处理，与 worktree 无关）
- rebase（统一用 merge，保留完整历史）
- push 到远端（由用户手动决定）
- stash 或中间分支
