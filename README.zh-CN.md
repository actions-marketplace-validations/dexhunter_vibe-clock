# vibe-clock

[English](README.md) | 简体中文 | [日本語](README.ja.md) | [Español](README.es.md)

**面向 AI 编程助手的 WakaTime。** 统计你使用 Claude Code、Codex、Gemini CLI 和 OpenCode 的情况，并展示在 GitHub 个人主页上。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/vibe-clock.svg)](https://pypi.org/project/vibe-clock/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/dexhunter/vibe-clock?style=social)](https://github.com/dexhunter/vibe-clock)

<p align="center">
  <img src="https://raw.githubusercontent.com/dexhunter/dexhunter/master/images/vibe-clock-card.svg" alt="Vibe Clock Stats" />
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/dexhunter/dexhunter/master/images/vibe-clock-donut.svg" alt="Model Usage" width="400" />
</p>

这些助手本来就会把会话日志写在你的磁盘上。vibe-clock 读取它们，默认全部留在本地；只有在你明确选择公开时，才会发布一份很小的、按白名单构造的摘要，再由 GitHub Action 渲染成主页上的 SVG。

---

## 快速开始

```bash
# 推荐方式 —— macOS、Linux 和 WSL 都适用
uv tool install vibe-clock      # 或者: pipx install vibe-clock, 或者: pip install vibe-clock
```

本文档描述的是 **1.5.0 及以上版本**；更早的版本没有 `vibe-clock setup` 和 `vibe-clock workflow`。可以用 `vibe-clock --version` 确认。

```bash
vibe-clock summary              # 在终端查看统计；数据不会离开本机

cd ~/path/to/your-profile-repo  # setup 会把工作流文件写进这个仓库目录
vibe-clock setup                # 准备好之后，再发布到你的主页
```

`vibe-clock setup` 会检测你的助手、在你装有 `gh` 时直接借用它的令牌、展示将要发布的确切 JSON、创建 Gist、设置仓库 secret、写入工作流文件，并安装每日推送任务。**任何会改动本机之外内容的步骤都会先征求同意**；它无法代劳的步骤会打印出操作说明。

剩下三件事需要你自己做，因为它们是对你自己仓库的提交、以及你自己浏览器里的一次点击：

1. 把下面的 `<img>` 标签加进你的主页 `README.md` —— `setup` 会打印出确切的代码块。
2. 把它和 `.github/workflows/vibe-clock.yml` 一起提交并推送。
3. 在仓库的 **Actions** 标签页手动运行一次工作流。之后就交给它的定时任务了。

如果在其他目录运行 `setup`，它只会打印工作流 YAML 让你手动保存，而不会写文件 —— 它不会往你指定仓库以外的目录里写东西。

<details>
<summary>其他安装方式</summary>

```bash
# 仅限 Apple Silicon 的 macOS（tap 提供的是 arm64 二进制，没有 Intel 或 Linux 版本）
brew install dexhunter/tap/vibe-clock
```

如果 `vibe-clock --version` 和你刚装的版本对不上，说明你装了两份。用 `which -a vibe-clock` 检查 —— 大多数 PATH 中 `~/.local/bin` 排在 `/opt/homebrew/bin` 前面，所以 `uv tool` 安装的会遮蔽 Homebrew 安装的。用 `uv tool upgrade vibe-clock` 或 `brew upgrade vibe-clock` 让两者一致。
</details>

## 发布什么，永远不发布什么

在你确认预览之前，任何数据都不会离开本机。这一点值得写清楚，下面是完整约定。

选择公开后**总是发布**的字段 —— 一共十个，这就是全部：

| 字段 | 示例 | 含义 |
|---|---|---|
| `schema_version`、`producer_version` | `3`、`"1.4.1"` | 让版本不匹配的读取端直接报错，而不是画出错误数字 |
| `generated_at` | `2026-08-24T00:00:00Z` | 推送日期，向下取整到 UTC 零点 —— 从不包含具体时刻 |
| `days_covered`、`active_days` | `7`、`5` | 统计窗口长度，以及其中有多少天使用过助手 |
| `total_sessions`、`total_minutes` | `12`、`321.0` | 会话数与活跃分钟数 |
| `active_agents` | `["claude_code", "codex"]` | 只会是固定四个名字中的若干个 |
| `favorite_model`、`models[]` | `"Claude"`、`[{"model": "OpenAI", "session_count": 3}]` | 模型**系列**及其会话数 |

**需要各自开关的可选项** —— 不传参数就不会发布：

| 参数 | 增加的内容 |
|---|---|
| `--daily-activity` | `daily[]`：每个日期一条记录及会话数。这会引入真实日历日期。 |
| `--time-patterns` | `hourly[]` 和 `peak_hour`：24 格的工作时段分布 |
| `--message-counts` | `total_messages`，以及按模型、按天的消息数 |
| `--token-counts` | `total_tokens`，以及按模型、按天的 token 数 |
| `--project-aliases` | `projects[]`，形如 `Project A`、`Project B`…… —— 绝不是真实名称 |

**无论开启哪个参数都不会发布：**

- 文件路径、目录名、你的主目录、你的用户名
- 真实的项目名或仓库名 —— 一律替换为 `Project A`、`Project B`……
- 原始模型 ID —— `claude-sonnet-4-6-20260101` 和 `gpt-5-codex-internal-preview` 会以 `Claude` 和 `OpenAI` 发布，因此内部或预览版模型名不会泄露
- 提示词、回复、代码、文件内容、工具调用
- 会话 ID、git 分支或远端、主机名、IP 地址
- 不属于上述四个已知助手的任何名字

真正提供保障的是 [`sanitizer.py`](vibe_clock/sanitizer.py) 中的白名单：载荷是按一组固定字段**构造**出来的，没有列出的字段根本发不出去；项目名在序列化之前就已被替换成别名，模型 ID 也已被映射到一个封闭的家族列表。它背后还有 `_validate_no_pii`，那是一道兜底断言 —— 它只复查少数几个来自你本机的文本字段，如果主目录路径或用户名居然通过了映射，就抛出异常而不是发布出去。它的作用是把将来的 bug 变成本地崩溃，而不是一个公开的 Gist；它并不是第二道独立的过滤器。请把白名单、而不是这道断言，当作真正的保证。

在发布任何东西之前，你都可以自己验证：

```bash
vibe-clock push --dry-run       # 逐字节打印确切的 JSON，什么也不发送
```

停止发布：`vibe-clock unshare` 会连同修订历史一起删除 Gist，并关闭后续更新。注意公开 Gist 会保留每一次历史修订，所以如果你发布了后悔的内容，删除 Gist 才是真正移除它的办法 —— 改个设置再推送一次是没用的。已经提交到主页仓库里的 SVG 是另一回事，需要在那边删除。

`vibe-clock export` 导出的是**未脱敏**的本地统计，包含真实项目名和模型 ID。它是给本地分析用的，不要把它的输出提交到仓库。它是唯一一个会把未脱敏数据写进文件的命令；`render` 不是，所以它生成的 SVG 可以放心提交。

## 这些数字是什么意思

**Agent Time（助手时长）** —— 卡片上的主要数字，也是最需要说清楚的一个。它是「你的某个助手正在写日志」的墙钟时间：先把日志事件按时间聚成一段段活动（静默超过五分钟就断开），再对所有会话取**并集**，所以两个助手同时跑，算的是一分钟而不是两分钟。

它不是给你本人计时。日志无法判断你是否坐在键盘前，所以一次通宵自动运行，和你全程盯着的会话是一样计入的。如果你经常跑长时间的无人值守任务，这个数字会比你的工作时间长 —— 那是机器的时间，卡片说的也正是这个。它被刻意命名为 Agent Time 而不是 Active Time，原因就在这里。

旧的算法是每个会话「最后一个事件减第一个事件」再求和。那会把午饭、整夜的空档、以及一个开了两周的 CLI 进程都算成使用量，还会把并发的助手重复计算；在作者本人的机器上，它算出了每天 59 小时。

**Sessions（会话数）** 统计的是各个助手各自定义的会话，而这个单位在不同助手之间并不一致：Codex 的一个会话是一个 rollout 文件，Claude Code 的一个会话是一个 `sessionId`。请和自己的历史比较，不要拿不同助手互相比较。

**Active Days（活跃天数）** 是窗口内任意助手有过非零活动时间的天数。

## 图表

```bash
vibe-clock render --type card,donut       # 把 SVG 写到当前目录
vibe-clock render --type all
```

`render` 构造的就是上面描述的那份白名单载荷，然后据此绘图 —— 无论它是在本机采集，还是用 `--from-json` 读取已发布的 Gist。两者画出的是同一张图，而且都不可能把真实项目名、路径或原始模型 ID 写进一个你即将提交的文件里。这也意味着 `render` 展示的是你的**公开**窗口（`privacy.public_days`，默认 7 天），并且只包含你的分享开关允许发布的数据 —— 想看不受限的本地视图请用 `vibe-clock summary`，要 JSON 就用 `vibe-clock export`。

| 图表 | 文件 | 需要 |
|-------|------|-------|
| `card` | `vibe-clock-card.svg` | — |
| `donut` | `vibe-clock-donut.svg` | — |
| `heatmap` | `vibe-clock-heatmap.svg` | `share --daily-activity` |
| `weekly` | `vibe-clock-weekly.svg` | `share --daily-activity` |
| `hourly` | `vibe-clock-hourly.svg` | `share --time-patterns` |
| `token_bars` | `vibe-clock-token-bars.svg` | `share --token-counts` |
| `bars` | `vibe-clock-bars.svg` | `share --project-aliases` |

如果某个图表所需的数据你从未共享，程序会直接拒绝并指出应加哪个参数，而不是画出一张空图。

## 保持更新

这里有两个时钟，两个都必须在跑：

```
本机                                      GitHub
────────────                              ──────
vibe-clock push        ──── 写入 ────▶    Gist（白名单 JSON）
（每天，约 00:00 UTC）                       │
                                             │ 被读取
                                             ▼
                                       Actions 工作流
                                       （每天 00:30 UTC）
                                             │
                                             ▼
                                       SVG 提交到
                                       你的主页仓库
```

Actions 的定时任务在本地推送半小时后运行，因此渲染的是新数据。只跑工作流，它会永远重画同样的数字；只跑推送，Gist 会更新但主页不会变。

`vibe-clock setup` 会替你安装本地这一半。若想单独操作：

```bash
vibe-clock schedule                  # 每天一次，时间为你本地对应 00:00 UTC 的时刻
vibe-clock schedule --interval hourly
vibe-clock unschedule
```

| 平台 | 后端 | 检查命令 |
|---|---|---|
| macOS | launchd 用户代理，`~/Library/LaunchAgents/com.vibe-clock.push.plist` | `launchctl list \| grep vibe-clock` |
| Linux | systemd **用户** timer，`~/.config/systemd/user/vibe-clock-push.timer` | `systemctl --user status vibe-clock-push.timer` |
| 任意 Unix | 上面两者都不可用时退回 crontab | `crontab -l \| grep vibe-clock` |
| Windows | 无后端 —— 请在 WSL 里运行 vibe-clock，或用任务计划程序调用 `vibe-clock push` | |

关于 Linux 的两点说明：

- systemd **用户** timer 在你退出登录后会被挂起。如果这台机器不会长期保持登录，请执行 `sudo loginctl enable-linger $USER`，让它继续触发。
- 生成的 unit 刻意保持为*用户*级，并且不设置 `ProtectHome`。若把它改成带 `ProtectHome=true` 的系统服务，它将无法执行 `$HOME` 下由 `uv tool` 或 `pipx` 安装的可执行文件，也读不到你的助手日志 —— 而那正是它唯一的工作。请让它留在用户会话中。

## 手动配置 GitHub Actions

`vibe-clock setup` 会完成下面所有事。这里逐条写出来，供不希望让工具直接改动仓库的人参考。

**1. 发布 Gist。** 你需要一个带 `gist` 权限的 **Classic** 个人访问令牌 —— [点此创建](https://github.com/settings/tokens/new?scopes=gist&description=vibe-clock)。fine-grained 令牌无法写 Gist。如果你已经在用 `gh`，`vibe-clock setup` 会借用它的令牌，这一步可以完全跳过。

```bash
vibe-clock push --dry-run       # 先检查
vibe-clock share                # 再次预览、征求同意，然后创建 Gist
```

记下它打印的 Gist ID。想附带可选数据就在这里加，例如 `vibe-clock share --daily-activity --token-counts`。

**2. 添加 secret。** 在你的主页仓库中：**Settings → Secrets and variables → Actions → New repository secret**，名称填 `VIBE_CLOCK_GIST_ID`，值填上一步的 ID。

**3. 添加工作流。** 创建 `.github/workflows/vibe-clock.yml`。运行 `vibe-clock workflow` 可以原样打印下面的内容，或在仓库目录中运行 `vibe-clock workflow --write` 直接写入：

```yaml
name: Update Vibe Clock Stats

on:
  schedule:
    # Runs after your local `vibe-clock push` updates the Gist.
    - cron: "30 0 * * *"
  workflow_dispatch:

# Required: the action commits the generated SVGs back to this repo, and
# GITHUB_TOKEN is read-only by default.
permissions:
  contents: write

concurrency:
  group: vibe-clock
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: dexhunter/vibe-clock@v1.5.0
        with:
          gist_id: ${{ secrets.VIBE_CLOCK_GIST_ID }}
          chart_types: card,donut
```

`permissions:` 这一段不是可选的：action 会把 SVG 提交回你的仓库，而 `GITHUB_TOKEN` 默认只读。缺少它会导致运行失败并报 403。

**4. 在主页 `README.md` 中引用这些 SVG：**

```html
<p align="center">
  <img src="images/vibe-clock-card.svg" alt="Vibe Clock Stats" />
  <img src="images/vibe-clock-donut.svg" alt="Model Usage" />
</p>
```

**5. 手动运行一次：** 仓库的 **Actions** 标签页 → *Update Vibe Clock Stats* → **Run workflow**。之后就交给定时任务。

**6. 配置本地定时推送** —— 见[保持更新](#保持更新)。跳过这一步，你的主页就会永远停留在第一次推送的内容上。

### Action 输入参数

| 参数 | 默认值 | 说明 |
|-------|---------|-------------|
| `gist_id` | *必填* | 包含 `vibe-clock-data.json` 的 Gist |
| `theme` | `dark` | `dark` 或 `light` |
| `output_dir` | `./images` | SVG 的写入目录 |
| `chart_types` | `card,donut` | 逗号分隔，或填 `all` |
| `commit` | `true` | 是否提交生成的 SVG |
| `commit_message` | `chore: update vibe-clock stats` | 提交信息 |

action 读取的是它所运行仓库的所有者的 Gist，因此无需任何修改即可在你自己的仓库中工作。

## 支持的助手

| 助手 | 日志位置 |
|-------|-------------|
| Claude Code | `~/.claude/` |
| Codex | `~/.codex/` |
| Gemini CLI | `~/.gemini/` |
| OpenCode | `~/.local/share/opencode/` |

自动检测。可在配置文件的 `[paths]` 中覆盖其中任意一项。

## 命令

| 命令 | 说明 |
|---------|-------------|
| `vibe-clock setup` | 完整引导：助手、Gist、仓库 secret、工作流、定时任务 |
| `vibe-clock summary` | 终端富文本汇总 —— 纯本地 |
| `vibe-clock status` | 同样的数字，压缩成一行 |
| `vibe-clock render` | 在本地生成 SVG |
| `vibe-clock workflow` | 打印需要安装的 Actions 工作流（`--write` 直接写入） |
| `vibe-clock init` | 只创建或刷新配置文件 |
| `vibe-clock export` | 把原始的**未脱敏**统计导出为本地 JSON |
| `vibe-clock push --dry-run` | 打印确切的公开载荷但不发送 |
| `vibe-clock share` | 预览、确认并启用公开 Gist |
| `vibe-clock push` | 更新已启用的公开分享 |
| `vibe-clock unshare` | 删除 Gist 及其修订历史，并停止发布 |
| `vibe-clock schedule` | 安装本地定时推送 |
| `vibe-clock unschedule` | 移除定时推送 |

## 配置

`~/.config/vibe-clock/config.toml`，以 `0600` 写入一个 `0700` 的目录中。

```toml
[general]
default_days = 30       # 本地命令的统计窗口；公开窗口由 privacy.public_days 决定
theme = "dark"          # dark | light

[paths]                 # 助手把日志放在别处时可覆盖
claude_code = "~/.claude"
codex = "~/.codex"
gemini_cli = "~/.gemini"
opencode = "~/.local/share/opencode"

[github]
token = ""              # Classic PAT，gist 权限
gist_id = ""            # 由 `share` / `setup` 设置
profile_repo = ""       # 渲染你 SVG 的 "owner/repo"
workflow_file = "vibe-clock.yml"   # 工作流文件名可自定义
trigger_workflow = false           # 见下文

[agents]
enabled = ["claude_code", "codex", "gemini_cli", "opencode"]

[privacy]
exclude_projects = []       # 通配符或纯子串，不区分大小写
exclude_date_ranges = []    # [["2026-01-01", "2026-01-07"], ...]
public_sharing_enabled = false
public_days = 7
share_daily_activity = false
share_message_counts = false
share_token_counts = false
share_time_patterns = false
share_project_aliases = false

[schedule]
enabled = false
interval = "daily"
time = "00:00"
backend = ""
```

环境变量覆盖：`GITHUB_TOKEN`（仅在 TOML 中的 token 为空时生效）、`VIBE_CLOCK_GIST_ID`、`VIBE_CLOCK_DAYS`。

`trigger_workflow` 让 `push` 立即触发渲染工作流，而不必等它的定时任务。它默认关闭，因为触发工作流需要带 **`repo`** 权限的令牌，而该权限可读写你的所有仓库 —— 远超其余功能所需的 `gist`。走定时任务这条路最多延迟一天，且不需要任何额外权限。

## 疑难排查

**工作流在 `git push` 处报 403。** 你的工作流缺少 `permissions: contents: write`。运行 `vibe-clock workflow` 对照一下。

**提示 "payload carries no schema_version" 或 "written by vibe-clock \<更旧的版本\>"。** 运行 `push` 的那台机器比渲染它的 action 更旧。升级它（`uv tool upgrade vibe-clock`）后重新推送。这个失败是刻意设计的 —— 否则每天都活跃的人会看到 `Active Days: 0`。

**提示 "chart 'hourly' needs hourly time patterns"。** 你要的图表需要未共享的数据。重新运行 `vibe-clock share --time-patterns`，或从 `chart_types` 里去掉该图表。

**安装后提示 `vibe-clock: command not found`。** `~/.local/bin` 可能不在 PATH 中；uv 安装可用 `uv tool update-shell` 解决。

**推送报 401。** 令牌是 fine-grained 的，或缺少 `gist` 权限。必须是 Classic PAT。

**Gist 更新了但主页没变。** 工作流没有运行。查看 Actions 标签页 —— 仓库连续 60 天无活动后，GitHub 会自动停用定时工作流。

**主页不再更新了。** 本地推送没在跑。用 `launchctl list | grep vibe-clock`、`systemctl --user status vibe-clock-push.timer` 或 `crontab -l` 检查。日志在 `~/.config/vibe-clock/logs/`。

**找不到会话。** 检查[支持的助手](#支持的助手)表中的目录是否存在且含有会话文件。

**README 里的 SVG 不刷新。** GitHub 对代理图片缓存很激进。等一会儿，或强制刷新。

## 参与贡献

欢迎提交 issue 和 PR —— 见 [CONTRIBUTING.md](CONTRIBUTING.md)。为另一个助手新增一个 collector 是最有价值、也是改动最小的贡献。

## 许可证

MIT
