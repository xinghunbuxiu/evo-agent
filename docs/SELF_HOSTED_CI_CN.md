# evo-agent：VPS 自托管 CI

## 现状与目标

原工作流使用 GitHub 托管的 `ubuntu-latest`。已将当前 PR 分支的 `.github/workflows/python-tests.yml` 改为使用仓库级 Linux VPS runner；在 VPS runner 注册并显示 Online 之前，新的测试 job 无法执行。安装步骤见下文。

原回归步骤保持不变：

1. Python 3.11
2. `python -m pip install -r requirements.txt`
3. `python -m unittest discover -s tests -v`

截至 2026-10-24，PR #1 之前最新记录的 Actions run #226 为失败；对应 job 没有暴露任何 steps，日志下载返回 404。这个证据**不能证明测试代码失败，也不能证明测试通过**。此前多个 run 有同样的无步骤失败表现。runner 上线后必须重新执行回归套件，才能判断实际测试结果。

## 目标架构

- GitHub 继续负责 Git 仓库、PR、提交记录和 Actions 编排。
- 测试进程运行在自己的 Linux VPS 上，使用仓库级标签 `self-hosted, linux, x64, evo-agent`。
- 不配置 VPS 部署密钥或应用生产凭据给测试 job；测试只读仓库内容。
- 依赖安装与测试命令保持和原 workflow 一致，避免迁移 CI 时顺便改变测试语义。

GitHub 官方当前文档将自托管 runner 的计算费用描述为免费，但 VPS、存储、带宽和维护仍由用户承担；计费政策可能变化，请以官方页面为准：
- https://docs.github.com/en/actions/concepts/billing-and-usage
- https://docs.github.com/en/actions/concepts/runners/self-hosted-runners

## 在 VPS 上安装（Debian/Ubuntu x86_64）

### 1. 创建专用账户

用 SSH 登录 VPS，以管理员执行（设置账户密码，后续 sudo 安装服务时会用到）：

```bash
sudo adduser evo-runner
sudo usermod -aG sudo evo-runner
sudo apt-get update
sudo apt-get install -y curl jq tar gzip ca-certificates
```

然后切换到专用账户：

```bash
sudo -iu evo-runner
```

### 2. 获取安装脚本

如果仓库公开，可执行：

```bash
git clone --branch automation/mission-learning-evidence-api-first https://github.com/xinghunbuxiu/evo-agent.git
cd evo-agent
bash scripts/install_github_runner.sh
```

如果仓库是私有的，不要把 PAT 写入 clone URL 或 shell 历史；请通过已有的安全文件传输通道把 `scripts/install_github_runner.sh` 复制到 VPS，再由专用账户执行。不要在长期 runner 用户下留下个人 GitHub 登录凭据。

脚本会从 GitHub 官方 `actions/runner` releases API 获取最新 Linux x64 runner，不把 runner registration token 写进仓库或命令历史，并安装为当前专用账户的 systemd 服务。不要以 root 身份运行 runner。

### 3. 生成短期注册令牌

打开仓库 Settings → Actions → Runners → New self-hosted runner，生成临时 registration token；运行脚本时在隐藏输入提示中粘贴。不要把令牌贴到聊天、Issue、代码、shell 命令参数或日志中。脚本只在本机使用令牌配置 runner。

### 4. 确认在线

在 Settings → Actions → Runners 中确认 runner 状态为 **Idle/Online**，标签包含 `self-hosted`、`linux`、`x64`、`evo-agent`。若未在线，先查看 VPS 上 runner service 的状态与日志，不要反复生成令牌。

## 运行安全边界

自托管 runner 执行仓库代码；恶意 PR 工作流可能尝试访问 runner 主机。因此：
- 仓库应保持私有，并限制谁可以创建/批准 PR 和修改 workflow。
- workflow 已跳过来自仓库外部 fork 的 PR，避免在持久 runner 上直接执行不可信代码。
- 不要把 runner 放在有生产凭据、SSH 私钥或其他敏感文件的主机账户下。
- 不要给测试 workflow 添加部署密钥。
- 建议 VPS 使用专用非 root 账户、及时更新系统，并限制网络访问。
- runner 是持久主机，不等同于每个 job 都干净销毁的临时虚拟机。

## 验收清单

1. GitHub runner 显示 Online/Idle。
2. 在 PR #1 分支提交一个小改动或手动触发 `Python regression tests`。
3. 确认 job 被标记为 `self-hosted` runner 执行，且能看到 checkout、依赖安装、unittest 步骤。
4. 查看 `python -m unittest discover -s tests -v` 的真实退出码与测试数。
5. 若失败，依据实际日志修复代码或环境；**不能**把 runner 上线等同于测试通过。

## 回滚

若 VPS runner 暂时不可用，将 workflow 的 `runs-on` 改回 `ubuntu-latest`；但这会重新依赖 GitHub 托管 runner 配额/可用性。也可在 Settings → Actions → Runners 删除离线 runner，并在 VPS 上运行 `sudo ~/actions-runner/svc.sh stop` 后按 GitHub 文档移除注册。
