# vibe-clock

[English](README.md) | [简体中文](README.zh-CN.md) | 日本語 | [Español](README.es.md)

**AI コーディングエージェント版 WakaTime。** Claude Code、Codex、Gemini CLI、OpenCode の利用状況を記録し、GitHub プロフィールに表示します。

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

エージェントはもともとセッションログをあなたのディスクに書き出しています。vibe-clock はそれを読み取り、既定ではすべてローカルに留めます。あなたが明示的に公開を選んだときだけ、許可リストに基づく小さな要約を発行し、GitHub Action がそれをプロフィール上の SVG に描画します。

---

## クイックスタート

```bash
# 推奨 — macOS、Linux、WSL で動作します
uv tool install vibe-clock      # または: pipx install vibe-clock, または: pip install vibe-clock
```

この README が説明するのは **1.5.0 以降**です。それより前のリリースには `vibe-clock setup` と `vibe-clock workflow` はありません。`vibe-clock --version` で確認してください。

```bash
vibe-clock summary              # 端末で統計を確認。データは端末から出ません

cd ~/path/to/your-profile-repo  # setup はこのチェックアウトにワークフローを書き込みます
vibe-clock setup                # 準備ができたら、プロフィールに公開します
```

`vibe-clock setup` はエージェントを検出し、`gh` があればそのトークンを借用し、公開する JSON をそのまま提示し、Gist を作成し、リポジトリの secret を設定し、ワークフローファイルを書き込み、毎日のプッシュを登録します。**この端末の外側を変更する操作は、すべて事前に確認を求めます。** 代行できない手順については、その手順を印字します。

そのあと、あなた自身が行う手順が 3 つ残ります。自分のリポジトリへのコミットと、自分のブラウザでのクリックだからです:

1. 下記の `<img>` タグをプロフィールの `README.md` に追加します — 正確なブロックは `setup` が印字します。
2. それと `.github/workflows/vibe-clock.yml` をコミットしてプッシュします。
3. リポジトリの **Actions** タブからワークフローを一度手動で実行します。以降は cron が引き継ぎます。

別の場所で `setup` を実行した場合、ファイルは書き込まれず、手で保存するためのワークフロー YAML が印字されます — 指定したリポジトリ以外のディレクトリには書き込みません。

<details>
<summary>その他のインストール方法</summary>

```bash
# macOS の Apple Silicon 専用（tap が配布するのは arm64 バイナリで、Intel 版も Linux 版もありません）
brew install dexhunter/tap/vibe-clock
```

`vibe-clock --version` が今入れたものと食い違う場合、2 つ入っています。`which -a vibe-clock` で確認してください。多くの PATH では `~/.local/bin` が `/opt/homebrew/bin` より先に来るため、`uv tool` 版が Homebrew 版を隠します。`uv tool upgrade vibe-clock` か `brew upgrade vibe-clock` で揃えてください。
</details>

## 何が公開され、何が決して公開されないか

プレビューを確認するまで、データは一切端末から出ません。ここは正確に書く価値があるので、取り決めの全文を示します。

公開に同意すると**必ず送られる**もの — 10 個で全部です:

| フィールド | 例 | 内容 |
|---|---|---|
| `schema_version`、`producer_version` | `3`、`"1.4.1"` | 版ずれのある読み取り側が、誤った数値を描かず明確に失敗するため |
| `generated_at` | `2026-08-24T00:00:00Z` | プッシュ日。UTC 0 時に切り捨て — 時刻そのものは含みません |
| `days_covered`、`active_days` | `7`、`5` | 集計期間の長さと、そのうち何日エージェントを使ったか |
| `total_sessions`、`total_minutes` | `12`、`321.0` | セッション数と実作業分数 |
| `active_agents` | `["claude_code", "codex"]` | 既知の 4 つの名前のみ |
| `favorite_model`、`models[]` | `"Claude"`、`[{"model": "OpenAI", "session_count": 3}]` | モデル**ファミリー**とセッション数 |

**フラグごとのオプトイン** — 指定しない限り送られません:

| フラグ | 追加されるもの |
|---|---|
| `--daily-activity` | `daily[]`: 日付ごとのセッション数。実際の暦日が加わります。 |
| `--time-patterns` | `hourly[]` と `peak_hour`: 24 区分の作業時間帯 |
| `--message-counts` | `total_messages` と、モデル別・日別のメッセージ数 |
| `--token-counts` | `total_tokens` と、モデル別・日別のトークン数 |
| `--project-aliases` | `projects[]` を `Project A`、`Project B`… として — 実名は決して使いません |

**どのフラグを立てても決して公開されないもの:**

- ファイルパス、ディレクトリ名、ホームディレクトリ、ユーザー名
- 実際のプロジェクト名やリポジトリ名 — `Project A`、`Project B`… に置き換えられます
- 生のモデル ID — `claude-sonnet-4-6-20260101` と `gpt-5-codex-internal-preview` は `Claude`、`OpenAI` として公開されるため、社内名やプレビュー名が漏れることはありません
- プロンプト、応答、コード、ファイル内容、ツール呼び出し
- セッション ID、git のブランチやリモート、ホスト名、IP アドレス
- 既知の 4 つ以外のエージェント名

保証しているのは [`sanitizer.py`](vibe_clock/sanitizer.py) の許可リストです。ペイロードは決まったフィールド集合から*組み立てられる*ため、そこに名前のないフィールドは送れません。プロジェクト名はシリアライズ前にエイリアスへ置き換えられ、モデル ID は閉じたファミリー一覧に写像されます。その背後にあるのが `_validate_no_pii` で、これは最後の砦としてのアサーションです — あなたの端末由来のテキストを持つ数個のフィールドだけを再確認し、ホームパスやユーザー名が写像を生き延びていた場合は、公開せずに例外を送出します。将来のバグを公開 Gist ではなくローカルのクラッシュに変えるためのものであり、独立した二番目のフィルタではありません。保証として読むべきは許可リストであって、このアサーションではありません。

公開する前に、自分で確かめられます:

```bash
vibe-clock push --dry-run       # 送信する JSON をそのまま表示し、何も送りません
```

やめるとき: `vibe-clock unshare` は Gist をリビジョン履歴ごと削除し、以後の更新を停止します。公開 Gist は過去のリビジョンをすべて保持するため、公開して後悔した内容を実際に消せるのは Gist の削除だけです — 設定を変えて再プッシュしても消えません。プロフィールリポジトリに commit 済みの SVG は別物なので、そちらで削除してください。

`vibe-clock export` が書き出すのは**サニタイズされていない**ローカル統計で、実際のプロジェクト名やモデル ID を含みます。ローカル分析用です。その出力を commit しないでください。サニタイズされていないデータをファイルに書くコマンドはこれだけです。`render` は違うので、その SVG は commit しても安全です。

## 数字の意味

**Agent Time（エージェント時間）** — カードの主役であり、いちばん丁寧に説明すべき数字です。あなたのエージェントのどれかがログを書いていた実時間で、ログイベントを連続したまとまりに区切り（5 分を超える沈黙で区切れます）、全セッションで**和集合**を取って求めます。2 つのエージェントが同時に動いても、2 分ではなく 1 分です。

これはあなたを計るストップウォッチではありません。ログからは、あなたがキーボードの前にいたかどうかは分かりません。夜通し走った自律実行も、ずっと見ていたセッションとまったく同じように数えられます。長時間の無人ジョブを回すなら、労働時間より大きな数字になります — それは機械の時間で、カードが言っているのもそれです。"Active Time" ではなく Agent Time という名前なのは、このためです。

以前の定義はセッションごとの「最後のイベント − 最初のイベント」の総和でした。昼食も、夜間の空白も、2 週間開きっぱなしの CLI プロセスも使用量として計上し、同時実行を二重に数えます。作者の端末では 1 日 59 時間という値が出ました。

**Sessions（セッション数）** は各エージェントがセッションと呼ぶものを数えたもので、単位はエージェント間で同じではありません。Codex のセッションは 1 つの rollout ファイル、Claude Code のセッションは 1 つの `sessionId` です。エージェント同士ではなく、自分の推移と比べてください。

**Active Days（アクティブ日数）** は、期間内でいずれかのエージェントの活動時間が 0 でなかった日数です。

## チャート

```bash
vibe-clock render --type card,donut       # カレントディレクトリに SVG を書き出す
vibe-clock render --type all
```

`render` は、ローカルで収集する場合も `--from-json` で公開済み Gist を読む場合も、上で説明した許可リスト済みペイロードを組み立て、そこから描画します。両者は同じ絵を出力し、どちらも実際のプロジェクト名・パス・生のモデル ID を、これから commit するファイルに入れることはできません。同時に、`render` が示すのは**公開**ウィンドウ（`privacy.public_days`、既定 7 日）であり、共有フラグが公開するデータだけです — 制限のないローカルの表示には `vibe-clock summary`、JSON なら `vibe-clock export` を使ってください。

| チャート | ファイル | 必要な共有 |
|-------|------|-------|
| `card` | `vibe-clock-card.svg` | — |
| `donut` | `vibe-clock-donut.svg` | — |
| `heatmap` | `vibe-clock-heatmap.svg` | `share --daily-activity` |
| `weekly` | `vibe-clock-weekly.svg` | `share --daily-activity` |
| `hourly` | `vibe-clock-hourly.svg` | `share --time-patterns` |
| `token_bars` | `vibe-clock-token-bars.svg` | `share --token-counts` |
| `bars` | `vibe-clock-bars.svg` | `share --project-aliases` |

共有していないデータを必要とするチャートは、空の図を描くのではなく、解決に必要なフラグ名を示して拒否されます。

## 更新を保つ

時計は 2 つあり、両方が動いている必要があります:

```
あなたの端末                              GitHub
────────────                              ──────
vibe-clock push        ──── 書き込み ──▶  Gist（許可リスト JSON）
（毎日、約 00:00 UTC）                       │
                                             │ 読み取り
                                             ▼
                                       Actions ワークフロー
                                       （毎日 00:30 UTC）
                                             │
                                             ▼
                                       SVG がプロフィール
                                       リポジトリに commit される
```

Actions の cron はローカルプッシュの 30 分後に動くので、新しいデータを描画します。ワークフローだけが動けば同じ数字を描き続け、プッシュだけが動けば Gist は更新されてもプロフィールは変わりません。

`vibe-clock setup` はローカル側を代わりに設定します。個別に行うなら:

```bash
vibe-clock schedule                  # 毎日、00:00 UTC に相当する現地時刻に実行
vibe-clock schedule --interval hourly
vibe-clock unschedule
```

| プラットフォーム | バックエンド | 確認コマンド |
|---|---|---|
| macOS | launchd ユーザーエージェント、`~/Library/LaunchAgents/com.vibe-clock.push.plist` | `launchctl list \| grep vibe-clock` |
| Linux | systemd **ユーザー** タイマー、`~/.config/systemd/user/vibe-clock-push.timer` | `systemctl --user status vibe-clock-push.timer` |
| その他の Unix | 上記が使えない場合の crontab | `crontab -l \| grep vibe-clock` |
| Windows | なし — WSL 内で vibe-clock を実行するか、タスク スケジューラで `vibe-clock push` を呼んでください | |

Linux についての注意 2 点:

- systemd の**ユーザー**タイマーはログアウトすると停止します。ログインし続けない端末では `sudo loginctl enable-linger $USER` を実行して、動き続けるようにしてください。
- 生成される unit は意図的に*ユーザー* unit のままで、`ProtectHome` を設定しません。`ProtectHome=true` のシステムサービスに移すと、`$HOME` にある `uv tool` や `pipx` のバイナリを実行できなくなり、エージェントのログも読めなくなります — それがこの仕事のすべてなのに。ユーザーセッションに置いたままにしてください。

## GitHub Actions を手動で設定する

`vibe-clock setup` は以下をすべて行います。ツールにリポジトリを触らせたくない人のために、手順を書き下します。

**1. Gist を公開する。** `gist` スコープを持つ **Classic** 個人アクセストークンが必要です — [ここで作成](https://github.com/settings/tokens/new?scopes=gist&description=vibe-clock)。fine-grained トークンは Gist を書けません。すでに `gh` を使っているなら `vibe-clock setup` がそのトークンを借用するので、この手順は丸ごと省けます。

```bash
vibe-clock push --dry-run       # まず内容を確認
vibe-clock share                # 再度プレビューし、確認のうえ Gist を作成
```

表示された Gist ID を控えてください。オプトインのデータを含めるならここで指定します。例: `vibe-clock share --daily-activity --token-counts`

**2. secret を追加する。** プロフィールリポジトリで **Settings → Secrets and variables → Actions → New repository secret**、名前を `VIBE_CLOCK_GIST_ID`、値をその ID にします。

**3. ワークフローを追加する。** `.github/workflows/vibe-clock.yml` を作成します。`vibe-clock workflow` を実行すると以下がそのまま出力され、リポジトリ内で `vibe-clock workflow --write` を実行すれば直接書き込まれます:

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

`permissions:` は省略できません。action は SVG をリポジトリに commit しますが、`GITHUB_TOKEN` は既定で読み取り専用です。これがないと 403 で失敗します。

**4. SVG をプロフィールの `README.md` から参照する:**

```html
<p align="center">
  <img src="images/vibe-clock-card.svg" alt="Vibe Clock Stats" />
  <img src="images/vibe-clock-donut.svg" alt="Model Usage" />
</p>
```

**5. 一度手動で実行する。** リポジトリの **Actions** タブ → *Update Vibe Clock Stats* → **Run workflow**。以降は cron が引き継ぎます。

**6. ローカルプッシュを登録する** — [更新を保つ](#更新を保つ)を参照。これを飛ばすと、プロフィールは最初のプッシュ内容のまま凍結します。

### Action の入力

| 入力 | 既定値 | 説明 |
|-------|---------|-------------|
| `gist_id` | *必須* | `vibe-clock-data.json` を含む Gist |
| `theme` | `dark` | `dark` または `light` |
| `output_dir` | `./images` | SVG の出力先 |
| `chart_types` | `card,donut` | カンマ区切り、または `all` |
| `commit` | `true` | 生成した SVG を commit する |
| `commit_message` | `chore: update vibe-clock stats` | コミットメッセージ |

action は実行されたリポジトリの所有者の Gist を読むので、あなたのリポジトリでもそのまま動きます。

## 対応エージェント

| エージェント | ログの場所 |
|-------|-------------|
| Claude Code | `~/.claude/` |
| Codex | `~/.codex/` |
| Gemini CLI | `~/.gemini/` |
| OpenCode | `~/.local/share/opencode/` |

自動検出されます。設定ファイルの `[paths]` で個別に上書きできます。

## コマンド

| コマンド | 説明 |
|---------|-------------|
| `vibe-clock setup` | 一括セットアップ: エージェント、Gist、secret、ワークフロー、スケジュール |
| `vibe-clock summary` | 端末での詳細サマリー — ローカルのみ |
| `vibe-clock status` | 同じ数値を 1 行で |
| `vibe-clock render` | ローカルで SVG を生成 |
| `vibe-clock workflow` | 導入すべき Actions ワークフローを出力（`--write` で保存） |
| `vibe-clock init` | 設定ファイルだけを作成・更新 |
| `vibe-clock export` | **サニタイズされていない**生の統計を JSON でローカル出力 |
| `vibe-clock push --dry-run` | 公開ペイロードをそのまま表示し、送信しない |
| `vibe-clock share` | プレビュー・確認のうえ公開 Gist を有効化 |
| `vibe-clock push` | 有効化済みの公開を更新 |
| `vibe-clock unshare` | Gist とリビジョンを削除し、公開を停止 |
| `vibe-clock schedule` | 定期ローカルプッシュを登録 |
| `vibe-clock unschedule` | それを解除 |

## 設定

`~/.config/vibe-clock/config.toml`。`0700` のディレクトリ内に `0600` で書かれます。

```toml
[general]
default_days = 30       # ローカルコマンドの集計期間。公開期間は privacy.public_days
theme = "dark"          # dark | light

[paths]                 # エージェントのログが別の場所にある場合に上書き
claude_code = "~/.claude"
codex = "~/.codex"
gemini_cli = "~/.gemini"
opencode = "~/.local/share/opencode"

[github]
token = ""              # Classic PAT、gist スコープ
gist_id = ""            # `share` / `setup` が設定
profile_repo = ""       # SVG を描画する "owner/repo"
workflow_file = "vibe-clock.yml"   # ワークフロー名は自由
trigger_workflow = false           # 下記参照

[agents]
enabled = ["claude_code", "codex", "gemini_cli", "opencode"]

[privacy]
exclude_projects = []       # グロブまたは単純な部分文字列。大文字小文字は区別しません
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

環境変数による上書き: `GITHUB_TOKEN`（TOML のトークンが空のときだけ有効）、`VIBE_CLOCK_GIST_ID`、`VIBE_CLOCK_DAYS`。

`trigger_workflow` を有効にすると、`push` が cron を待たずに描画ワークフローを即座に起動します。既定で無効なのは、ワークフローの起動に **`repo`** スコープのトークンが必要で、それが全リポジトリへの読み書き権限を与えるからです — 他のすべてに必要な `gist` よりはるかに広い権限です。cron に任せれば、遅延は最大 1 日で、追加の権限は要りません。

## トラブルシューティング

**ワークフローが `git push` で 403 になる。** ワークフローに `permissions: contents: write` がありません。`vibe-clock workflow` の出力と見比べてください。

**"payload carries no schema_version" や "written by vibe-clock \<より古い版\>" と出る。** `push` を実行している端末が、描画する action より古いです。`uv tool upgrade vibe-clock` で更新して再プッシュしてください。この失敗は意図的です — 代わりに起きていたのは、毎日活動していた人に `Active Days: 0` と表示することでした。

**"chart 'hourly' needs hourly time patterns" と出る。** 共有していないデータを使うチャートを要求しています。`vibe-clock share --time-patterns` を実行し直すか、`chart_types` からそのチャートを外してください。

**インストール後に `vibe-clock: command not found`。** `~/.local/bin` が PATH にない可能性があります。uv なら `uv tool update-shell` で解決します。

**プッシュが 401 で失敗する。** トークンが fine-grained か、`gist` を欠いています。Classic PAT である必要があります。

**Gist は更新されるのにプロフィールが変わらない。** ワークフローが動いていません。Actions タブを確認してください — リポジトリが 60 日間活動しないと、GitHub はスケジュール実行を自動で無効化します。

**プロフィールの更新が止まった。** ローカルプッシュが動いていません。`launchctl list | grep vibe-clock`、`systemctl --user status vibe-clock-push.timer`、`crontab -l` で確認してください。ログは `~/.config/vibe-clock/logs/` にあります。

**セッションが見つからない。** [対応エージェント](#対応エージェント)の表にあるディレクトリが存在し、セッションファイルを含んでいるか確認してください。

**README の SVG が更新されない。** GitHub はプロキシ画像を強くキャッシュします。少し待つか、強制再読み込みしてください。

## コントリビュート

Issue や Pull Request を歓迎します — [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。別のエージェント向けの collector を追加するのが、もっとも有用でもっとも小さい貢献です。

## ライセンス

MIT
