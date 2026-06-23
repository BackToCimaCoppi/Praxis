# git-worktree

> 多 worktree 并行开发的生命周期管家：新建、合并回主干、主干同步下发、清理，一个菜单全包。

## 这是什么

一个围绕 git worktree 的全生命周期管理流程。把「一个仓库同时开几条活线」这件事标准化：`master`（主仓库）是唯一主干，每条并行开发线是一个独立 worktree（独立目录、独立分支），所有改动最终都 merge 回 master。

触发后先弹菜单，四选一：

- **新建 worktree**：从 master 拉新分支，在主仓库的兄弟目录建一个 worktree。
- **合并到 master**：当前 worktree 完工，commit 后 merge 回 master。
- **master 同步到所有 worktree**：master 有重大改动时，把它 merge 进每个 feature worktree。
- **清理当前 worktree**：确认已全部合并后，删掉 worktree 和分支。

边界：

- **管**：worktree 的创建/合并/同步/删除，以及这些操作里的提交顺序。
- **不管**：任务激活切换（另有 `/control switch`，与 worktree 解绑——同一 worktree 可承载多个任务）、rebase（一律用 merge 保留完整历史）、push 到远端（你手动决定）、stash 或中间分支（不用）。

## 解决什么问题

不用它时，手工玩多 worktree 容易出这些乱子：

1. **worktree 建错地方**：随手建在主仓库子目录里，结果它的文件全冒进主仓库的 `git status`，污染主干工作区。
2. **合并时丢改动**：merge 前忘了提交源分支或目标分支的未提交改动，merge 完一脸懵——东西去哪了。
3. **同步主干顺序混乱**：master 改了共享依赖/接口，挨个 worktree 手动 merge，中途某个冲突了不知道停在哪、漏掉哪几个没同步。
4. **删早了丢代码**：worktree 里还有没合并回 master 的 commit 就 `worktree remove --force`，提交直接蒸发。

## 为什么这么设计

- **统一的合并原则**：所有涉及合并的操作都按固定顺序——先提交**源分支**未提交改动、再提交**目标分支**未提交改动、然后 merge、遇冲突直接解决（不 stash、不建中间分支）。顺序固定，保证 merge 时两边都处于干净已提交状态，不丢东西。
- **master 是唯一主干**：所有 worktree 最终回流 master，不搞多主干。`--no-ff` 合并保留分支痕迹，历史清晰可追。
- **目录命名与位置强约束**：worktree 目录名 `{repo}-{名称}`（单横线，`{repo}` 是主仓库目录名），放在主仓库的**兄弟目录**，禁止放进主仓库任何子目录——从根上避免污染 git status。
- **删除前双重验证 + 不自动 force**：清理前必须同时确认「无未提交改动」「无未合并到 master 的 commit」两项才删；`worktree remove` 报错时停下交给你处理，AI 绝不自作主张加 `--force`。安全优先于便利。

## 怎么用

1. **触发词**

   「创建 worktree」「新建 worktree」「worktree 合并」「合并到 master」「master 同步」「同步所有 worktree」「清理 worktree」「git worktree」「worktree 管理」。

2. **流程**（先弹菜单，再按所选分支走）

   - **新建（§A）**：问你一个英文任务名（如 `poster-render`）→ 更新 master → 在兄弟目录 `{repo}-{名称}` 建 worktree、拉 `feature/{名称}` 分支 → 列出验证 → 告知完整路径和分支名。
   - **合并到 master（§B）**：先提当前 worktree 改动（有则确认 message 后 commit）→ 再提 master 改动 → `merge <当前分支> --no-ff` 进 master → 有冲突就展示冲突文件、协助逐个解决、`git add` 后 commit → 看 `log` 验证。
   - **master 同步到所有 worktree（§C）**：遍历每个 feature worktree → 各自有未提交改动先 `wip` 提交 → `merge master --no-ff` → 某个冲突就**停下**，报出冲突 worktree 路径，等你进去解决后重新触发同步。
   - **清理当前 worktree（§D）**：验证无未提交改动、无未合并 commit → 都干净才 `worktree remove` + `branch -d` → 有未合并 commit 则提示先去 §B 合并；`remove` 报错则停下报告，不强删。

3. **最小示例**

   ```
   输入：给海报渲染开一条并行开发线

   选择：新建 worktree
   任务名：poster-render

   产出：
     新 worktree 路径：<主仓库兄弟目录>/{repo}-poster-render
     分支：feature/poster-render（从最新 master 拉出）
   ```

   ```
   输入：海报渲染做完了，合回主干

   选择：合并到 master
     → 当前 worktree 有改动，确认 message 后提交
     → master 干净，跳过
     → git -C <主仓库> merge feature/poster-render --no-ff
   产出：feature/poster-render 已合入 master（保留合并节点）
   ```

4. **常见坑**

   - **worktree 建进主仓库子目录**：会污染主干 git status，必须放兄弟目录。
   - **同步时遇冲突却想继续遍历**：§C 遇冲突会停在那个 worktree，必须先进去解决再重新触发，不会跳过它往下跑。
   - **没合并就想清理**：§D 检测到有未合并到 master 的 commit 会拦下，先走 §B 合并。
   - **指望 AI 帮你 `--force` 删**：不会。`worktree remove` 报错一律停下交还给你。
   - **以为合并会顺便 push**：不会。push 到远端始终是你手动决定。
