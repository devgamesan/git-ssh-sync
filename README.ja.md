[![日本語](https://img.shields.io/badge/lang-日本語-blue)](README.ja.md) [![English](https://img.shields.io/badge/lang-English-brightgreen)](README.md)

# git-ssh-sync

[![CI](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Release](https://img.shields.io/github/v/release/devgamesan/git-ssh-sync)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`git-ssh-sync` は、GitHub / GitLab に直接アクセスできない開発環境で作成した Git コミットを、ローカルマシン経由で外部 Git サービスへ同期するための CLI ツールです。

このツールは、SSH や RDP などの限定されたインバウンド通信のみが許可され、アウトバウンド通信が制限されているニッチな環境（高セキュリティ企業のプロジェクトなど）を対象に設計されています。

## 想定ユーザー

`git-ssh-sync` は次のような環境向けです。

- 開発環境から GitHub / GitLab に直接アクセスできない
- ローカルマシンからは GitHub / GitLab にアクセスできる
- ローカルマシンから開発環境へ SSH 接続できる
- 編集、ビルド、テスト、コミットは開発環境で行いたい
- ファイルコピーではなく Git commit / branch 単位で同期したい

開発環境から GitHub / GitLab に直接アクセスできる通常の Git 環境では、基本的にこのツールは不要です。

このツールはファイル同期ツールではありません。同期するのは Git オブジェクトとブランチです。ソース編集、ビルド、テスト、コミットは開発環境で行い、GitHub / GitLab との通信はローカルマシンで行います。

## アーキテクチャ

`git-ssh-sync` は、GitHub / GitLab へのアクセスをローカルマシンに寄せ、
Git 作業を開発環境上で行う構成を取ります。

```text
origin: GitHub / GitLab
    ↑↓
local gateway repo
    ↑↓ git over SSH
dev bare cache repo
    ↑↓
dev work repo
```

この README では、次の用語を使います。

- `origin`: GitHub / GitLab 側の本来の remote repository
- `local gateway repo`: ローカルマシン上の中継用 repository
- `dev bare cache repo`: 開発環境上の bare repository
- `dev work repo`: 開発環境上で実際に編集、ビルド、テスト、commit する repository
- `gitsync remote`: dev work repo から dev bare cache repo を参照するための remote

## 現在の制限

現時点では次の機能には対応していません。

- Git LFS
- Git submodule
- 自動コンフリクト解決
- 未コミット変更の同期

## 前提

`git-ssh-sync` は次のような構成を前提にしています。

```text
GitHub / GitLab
    ↑↓
ローカルマシン
    ↑↓ SSH
開発環境
```

ローカルマシン:

- GitHub / GitLab にアクセスできる
- 開発環境へ SSH 接続できる
- `git` と `uv` を利用できる
- `git-ssh-sync` で GitHub / GitLab と開発環境の間のコミット同期、状態確認、診断を行う

開発環境:

- ローカルマシンから SSH 接続できる
- 開発環境から GitHub / GitLab に直接アクセスできない
- `git` を利用できる
- ソース編集、ビルド、テスト、コミットを行う
- GitHub / GitLab との同期はローカルマシン経由で行う

## 安全モデル

`git-ssh-sync` は次のことを行いません。

- 未コミットファイルの同期
- 自動 merge / 自動 rebase
- origin への force push
- dirty な開発環境 work repo の自動変更
- 開発環境への GitHub / GitLab 認証情報の配置
- 開発環境から GitHub / GitLab への直接 outbound 接続

## インストール

通常利用では、ローカルマシンに `uv tool install` でインストールして使います。

```bash
uv tool install git-ssh-sync
```

未リリース版やリポジトリの最新版を使う場合は、GitHub から直接インストールします。

```bash
uv tool install git+https://github.com/devgamesan/git-ssh-sync.git
```

インストール後、コマンドが実行できることを確認します。

```bash
git-ssh-sync --help
```

## クイックスタート

`git-ssh-sync` のインストール後、設定から日常同期までの最短手順は次のとおりです。

```bash
uv tool install git-ssh-sync

git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject

git-ssh-sync clone myproject
git-ssh-sync doctor myproject

git-ssh-sync pull myproject

# 開発環境上:
# cd ~/work/myproject
# git add .
# git commit -m "Add feature"

git-ssh-sync status myproject
git-ssh-sync push myproject
```

初回セットアップでは `clone` と `doctor` まで実行します。日常作業では、編集前に
ローカルマシンから `pull` し、開発環境で commit してから、ローカルマシンで
`status` を確認して `push` します。

## 設定

最初に、同期したいプロジェクトを登録します。

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject
```

主な指定内容は次のとおりです。

- `myproject`: `git-ssh-sync` 上のプロジェクト名
- `--origin`: GitHub / GitLab 側のリポジトリ URL
- `--dev-host`: 開発環境の SSH ホスト
- `--dev-user`: 開発環境の SSH ユーザー
- `--dev-os`: 開発環境の OS。`posix` または `windows`（デフォルト: `posix`）
- `--dev-path`: 開発環境上の work repo パス

開発環境が Windows の場合は `--dev-os windows` を指定し、Windows パスを使います。
Windows への SSH コマンドは PowerShell 経由で実行します。

```powershell
git-ssh-sync init myproject `
  --origin git@github.com:example/myproject.git `
  --dev-host devserver `
  --dev-user user `
  --dev-os windows `
  --dev-path 'C:\Users\user\work\myproject'
```

macOS や Linux の `zsh` / `bash` から実行する場合、バックスラッシュを含む Windows パスは
引用してください。引用しないと、`git-ssh-sync` に渡る前に shell が `\` を削除することが
あります。代わりに `C:/Users/user/work/myproject` のような `/` 区切りも使えます。

`--dev-os windows` を指定した場合、cache path のデフォルトは
`C:\Users\<dev-user>\.git-ssh-sync\cache\<project>.git` です。`clone` は開発環境上に
設定済みの work path または cache path が既に存在する場合に停止します。古いディレクトリを
削除するか、既存リポジトリを使う場合は attach / recover のワークフローを使ってください。

`--origin` には、`git clone` や `git fetch` で指定できるリモート URL を指定します。主な形式は次のとおりです。

```text
git@github.com:example/myproject.git
git@gitlab.com:example/myproject.git
ssh://git@github.com/example/myproject.git
https://github.com/example/myproject.git
https://gitlab.com/example/myproject.git
```

SSH 形式を使う場合、GitHub / GitLab へ接続するための SSH 鍵や認証設定はローカルマシン側に用意してください。開発環境から GitHub / GitLab へは直接接続しません。

登録済みの設定を上書きする場合は `--force` を付けます。

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject \
  --force
```

### 設定ファイル

プロジェクト設定は YAML として保存されます。保存先は `git-ssh-sync` を実行する
ローカルマシンの OS によって異なります。

```text
macOS / Linux: ~/.config/git-ssh-sync/config.yaml
Windows:       %APPDATA%\git-ssh-sync\config.yaml
```

生成される設定は次のような形式です。

```yaml
version: 1

projects:
  myproject:
    origin: git@github.com:example/myproject.git

    local:
      repo_path: ~/.git-ssh-sync/repos/myproject

    dev:
      host: devserver
      user: user
      os: posix
      work_path: /home/user/work/myproject
      cache_path: /home/user/.git-ssh-sync/cache/myproject.git

    options:
      sync_tags: true
      lfs: false
      submodules: false
      ff_only: true
```

主な項目は次のとおりです。

- `origin`: ローカル側の gateway repo が使う GitHub / GitLab リポジトリ URL
- `local.repo_path`: `git-ssh-sync` が管理するローカル側 gateway repo のパス
- `dev.host`, `dev.user`, `dev.os`: SSH 接続先と開発環境の OS
- `dev.work_path`: 開発環境上の work repo パス
- `dev.cache_path`: 開発環境上の bare cache repo パス
- `options.sync_tags`: pull / push 時に Git tag を同期するかどうか
- `options.lfs`: Git LFS 対応用の予約設定
- `options.submodules`: submodule 対応用の予約設定
- `options.ff_only`: fast-forward のみで同期するかどうか

通常は `git-ssh-sync init` と `git-ssh-sync config` コマンドでこのファイルを管理します。
手動で編集する場合は YAML の構造を変えず、各項目が使われるローカルマシンまたは開発環境で有効なパスを指定してください。

設定ファイルを直接開かなくても、登録済みプロジェクトを確認・整理できます。

```bash
# 登録済みプロジェクトを一覧表示
git-ssh-sync config list

# 1 つのプロジェクトの全設定を表示
git-ssh-sync config show myproject

# 指定した設定だけを更新
git-ssh-sync config set myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-os posix \
  --dev-path /home/user/work/myproject

# 確認後にプロジェクトを削除
git-ssh-sync config remove myproject

# 非対話でプロジェクトを削除
git-ssh-sync config remove myproject --yes
```

## 初回 workflow

初回は、設定作成、開発環境への clone、診断の順に実行します。

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject
git-ssh-sync clone myproject
git-ssh-sync doctor myproject
```

`clone` は上記の local gateway repo を作成し、開発環境に dev bare cache repo と
dev work repo を配置します。

以後、開発環境では work repo を通常の Git リポジトリとして扱えます。

`doctor` はローカル環境、SSH 接続、origin への fetch / push 権限、開発環境側のリポジトリ配置を確認します。初回だけでなく、同期がうまくいかない時にも最初に実行してください。

## 既存リポジトリの取り込み

gateway repo、開発環境の work repo、cache repo がすでに存在する場合は、
`clone` ではなく `attach` を使います。

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject
git-ssh-sync attach myproject --dry-run
git-ssh-sync attach myproject
git-ssh-sync doctor myproject
```

`attach` は、設定された origin URL、現在ブランチ、開発環境 work repo の
dirty 状態、bare cache repo、`gitsync` remote を検査します。変更前に実行
予定の操作を表示します。内容確認済みで非対話実行したい場合は `--yes` を
付けます。

```bash
git-ssh-sync attach myproject --yes
```

初期診断、紐付け修復、同期中断後の復旧入口は、次の表を目安に使い分けます。

| 状況 | 使うコマンド |
|---|---|
| 初期設定や接続状態を確認したい | `git-ssh-sync doctor myproject` |
| `gitsync` remote や cache の紐付けを修復したい | `git-ssh-sync doctor myproject --repair` |
| `pull` / `push` が途中停止した後に状態確認したい | `git-ssh-sync recover myproject` |
| 中断後に安全な紐付け修復だけ実行したい | `git-ssh-sync recover myproject --yes` |

`gitsync` remote や cache との紐付けだけが不足・不一致の場合は、
`doctor --repair` でも同じ preflight check を通して修復できます。

```bash
git-ssh-sync doctor myproject --repair
git-ssh-sync doctor myproject --repair --yes
```

`pull` / `push` が途中停止した後は、復旧用の入口として `recover` を
使います。`--yes` なしでは origin、gateway、cache、work repo の状態を
診断し、具体的な次の操作を表示します。`--yes` 付きでは、cache repo の
作成、cache branch の投入、`gitsync` remote の修正など、安全な紐付け修復
だけを実行します。

```bash
git-ssh-sync recover myproject
git-ssh-sync recover myproject --yes
```

`attach` と `doctor --repair` は、既存作業の commit、stash、merge、rebase
は行いません。開発環境 work repo が dirty な場合や、指定パスが互換性の
ある Git リポジトリではない場合は停止し、手動復旧手順を表示します。

## 日常開発 workflow

日常開発では、作業開始前にローカルマシンから `pull` し、開発環境で通常どおりコミットし、最後にローカルマシンから `push` します。

ローカルマシン:

```bash
git-ssh-sync pull myproject
```

開発環境:

```bash
cd ~/work/myproject
git status
git add .
git commit -m "Add feature"
```

ローカルマシン:

```bash
git-ssh-sync push myproject
```

`pull` と `push` は、開発環境 work repo のカレントブランチを対象にします。別のブランチを同期したい場合は、先に `checkout` で work repo のブランチを切り替えます。

作業開始時に状態が分からない場合は、まずローカルマシンで同期状態を確認し、必要に応じて `pull` します。

```bash
git-ssh-sync status myproject
git-ssh-sync pull myproject
git-ssh-sync dev status myproject
```

`dev status` で開発環境の作業ツリーが dirty な場合、未コミット変更は同期されません。開発環境で差分を確認し、同期したい変更を commit してから `push` してください。

```bash
git-ssh-sync dev diff myproject --stat
```

push 前は、開発環境で commit 済みであることを確認してから、ローカルマシンで `status` と `push` を実行します。

```bash
git-ssh-sync status myproject
git-ssh-sync push myproject
```

ref を変更する前に実行予定の操作と preflight check を確認するには `--dry-run` を使います。

```bash
git-ssh-sync pull myproject --dry-run
git-ssh-sync push myproject --dry-run
```

## push が止まった時の workflow

`push` は origin 側のブランチが開発環境側のブランチの祖先である場合だけ実行します。origin に未取得のコミットがある場合や、origin と開発環境が分岐している場合は停止します。

この場合は、ローカルマシンで `pull` を実行して origin の変更を開発環境へ届けます。

```bash
git-ssh-sync pull myproject
```

`pull` が fast-forward できない場合、自動 merge や自動 rebase は行いません。開発環境で通常の Git 操作として merge または rebase を行い、必要に応じてコンフリクトを解消してから、ローカルマシンで再度 `push` します。

merge で解決する例:

```bash
cd ~/work/myproject
git fetch gitsync
git merge gitsync/main
# コンフリクトした場合はファイルを修正する
git status
git add <resolved-files>
git commit
```

rebase で解決する例:

```bash
cd ~/work/myproject
git fetch gitsync
git rebase gitsync/main
# コンフリクトした場合はファイルを修正する
git status
git add <resolved-files>
git rebase --continue
```

ブランチ名が `main` 以外の場合は、`gitsync/main` を対象ブランチに置き換えてください。merge または rebase が完了したら、ローカルマシンで状態を確認してから push します。

```bash
git-ssh-sync status myproject
git-ssh-sync push myproject
```

rebase 後の履歴を書き換えた commit は、まだ origin へ push されていない開発環境側の commit だけにしてください。共有済みブランチで履歴を書き換える運用を避けたい場合は merge を選んでください。

## ブランチ切り替え workflow

既存ブランチへ切り替える場合は、ローカルマシンから `checkout` を実行します。

ローカルマシン:

```bash
git-ssh-sync checkout myproject feature/foo
```

新しいブランチを作る場合は `-b` を付けます。起点を明示する場合は `--base` を併用します。

```bash
git-ssh-sync checkout myproject -b feature/foo --base develop
```

origin、cache、work repo の ref を変更せずにブランチ切り替えやブランチ作成を確認するには、`checkout` にも `--dry-run` を付けます。

```bash
git-ssh-sync checkout myproject feature/foo --dry-run
git-ssh-sync checkout myproject -b feature/foo --base develop --dry-run
```

開発環境:

```bash
cd ~/work/myproject
git status
git add .
git commit -m "Implement foo"
```

ローカルマシン:

```bash
git-ssh-sync push myproject
```

`checkout -b feature/foo --base develop` は、origin の `develop` を元に origin 上へ `feature/foo` を作成し、開発環境の work repo をそのブランチへ切り替えます。`--base` を省略した場合は、開発環境 work repo のカレントブランチを起点にします。すでに origin に同名ブランチがある場合は、`-b` なしで既存ブランチへ切り替えてください。

## 状態確認

同期状態を確認するには `status` を使います。

```bash
git-ssh-sync status myproject
```

`status` は、開発環境 work repo のカレントブランチを対象に、origin と開発環境の ahead / behind、作業ツリー状態を表示します。表示された recommendation に従って、必要に応じて `pull` または `push` を実行してください。

ブランチごとの存在状況や ahead / behind を一覧するには `branch` を使います。

```bash
git-ssh-sync branch myproject
```

ローカルマシンから開発環境 work repo の状態を直接確認するには、参照専用の
`dev` コマンドを使います。

```bash
git-ssh-sync dev status myproject
git-ssh-sync dev diff myproject
git-ssh-sync dev diff myproject --stat
git-ssh-sync dev log myproject --max-count 5
```

これらのコマンドは SSH 越しに開発環境 work repo で `git status`、
`git diff`、`git log` を実行します。origin、ローカル gateway repo、
開発環境 cache repo、開発環境 work repo の ref は更新しません。

## 運用ルール

`git-ssh-sync` を使う時は、次のルールを守ると状態を把握しやすくなります。

- 作業開始前にローカルマシンで `pull` する
- コミットは開発環境で作る
- 作業が終わったらローカルマシンで `push` する
- 同期前後で迷ったら `status` を見る
- 接続やリポジトリ配置に不安がある時は `doctor` を実行する

未コミット変更は同期されません。開発環境の作業ツリーに未コミットの変更がある場合、その変更自体はローカルマシンや origin には送られません。同期したい変更は、開発環境で `git add` と `git commit` を済ませてください。

`pull` は fast-forward できる場合だけ開発環境のブランチを更新します。origin と開発環境が分岐している場合、自動 merge や自動 rebase は行いません。

`push` は origin 側のブランチが開発環境側のブランチの祖先である場合だけ実行します。origin に未取得のコミットがある場合は停止します。

分岐した場合は自動では解決しません。「push が止まった時の workflow」に従い、開発環境で merge または rebase を行ってから、再度 `push` してください。

## よく使うコマンド

```bash
# ヘルプを表示
git-ssh-sync --help

# プロジェクトを登録
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject

# 登録済みプロジェクト設定を一覧表示
git-ssh-sync config list

# 登録済みプロジェクト設定を表示
git-ssh-sync config show myproject

# 初回 clone
git-ssh-sync clone myproject

# 同期状態を確認
git-ssh-sync status myproject

# ブランチ状態を確認
git-ssh-sync branch myproject

# 開発環境 work repo の状態を確認
git-ssh-sync dev status myproject

# 開発環境 work repo の差分を確認
git-ssh-sync dev diff myproject --stat

# origin の変更を開発環境へ反映
git-ssh-sync pull myproject

# 開発環境のコミットを origin へ反映
git-ssh-sync push myproject

# 開発環境のブランチを切り替え
git-ssh-sync checkout myproject feature/foo

# ベースブランチから新規ブランチを作成して切り替え
git-ssh-sync checkout myproject -b feature/foo --base develop

# 診断
git-ssh-sync doctor myproject

# 同期中断後の診断と安全な修復
git-ssh-sync recover myproject
git-ssh-sync recover myproject --yes
```

## トラブルシューティング

同期が止まった時や現在の状態が分からない時は、まず `status` を使います。
初期設定、接続、リポジトリの紐付けに問題がありそうな時は `doctor` を使います。
`pull` / `push` が途中停止した後は `recover` を使います。

### push が止まる

Cause:
origin に、開発環境ブランチへまだ取り込まれていない commit があるか、
origin と開発環境ブランチが分岐しています。

Check:

```bash
git-ssh-sync status myproject
```

Fix:

```bash
git-ssh-sync pull myproject
# pull が fast-forward できない場合は、開発環境で merge または rebase します。
# 詳細は「push が止まった時の workflow」を参照してください。
```

### pull が fast-forward できない

Cause:
origin と開発環境ブランチが分岐しています。`git-ssh-sync` は自動 merge や
自動 rebase を行いません。

Check:

```bash
git-ssh-sync status myproject
git-ssh-sync dev status myproject
```

Fix:

```bash
# 開発環境で実行
cd ~/work/myproject
git fetch gitsync
git merge gitsync/main
# または: git rebase gitsync/main
```

コンフリクト解消後に commit するか rebase を継続したら、ローカルマシンで
以下を実行します。

```bash
git-ssh-sync status myproject
git-ssh-sync push myproject
```

### 開発環境 work repo が dirty

Cause:
開発環境 work repo に未コミット変更があります。未コミット変更は同期されません。
修復コマンドも、既存作業の commit、stash、merge、rebase は自動実行しません。

Check:

```bash
git-ssh-sync dev status myproject
git-ssh-sync dev diff myproject --stat
```

Fix:

```bash
# 開発環境で実行
cd ~/work/myproject
git status
git add <files-to-sync>
git commit
```

同期したい変更は commit し、ローカルだけの変更は stash または削除してから
`pull`、`push`、`attach`、`doctor --repair` を再実行してください。

### gitsync remote が不一致

Cause:
開発環境 work repo の `gitsync` remote が想定した bare cache repo を指していない、
または remote / cache の紐付けが不足しています。

Check:

```bash
git-ssh-sync doctor myproject
```

Fix:

```bash
git-ssh-sync doctor myproject --repair
git-ssh-sync doctor myproject --repair --yes
```

### cache repo / work repo が既に存在する

Cause:
`clone` が作成しようとしている開発環境 work repo または bare cache repo のパスが
既に存在しています。

Check:

```bash
git-ssh-sync doctor myproject
```

Fix:

```bash
git-ssh-sync attach myproject --dev-path /home/user/work/myproject
git-ssh-sync doctor myproject --repair
```

既存リポジトリを使う場合は `attach` を使います。そうでない場合は、空のパスを
指定するか、既存ディレクトリを移動してから `clone` を再実行してください。

### Windows path が壊れる

Cause:
ローカル shell が Windows パスのバックスラッシュを `git-ssh-sync` に渡す前に
解釈しているか、開発環境 OS の設定が誤っています。

Check:

```bash
git-ssh-sync config show myproject
git-ssh-sync doctor myproject
```

Fix:

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-os windows \
  --dev-path 'C:\Users\user\work\myproject'
```

macOS や Linux の shell から実行する場合は、バックスラッシュを含む Windows パスを
quote してください。

### SSH 接続できない

Cause:
ローカルマシンから開発環境へ SSH 接続できないか、設定済みの host、user、port、
認証設定が誤っています。

Check:

```bash
git-ssh-sync doctor myproject
ssh user@devserver
```

Fix:

```bash
git-ssh-sync config show myproject
# 正しい --dev-host、--dev-user、--dev-port、SSH 認証設定で
# プロジェクト設定を更新するか、作り直してください。
```

診断時に実行された SSH / Git コマンドを確認したい場合は、`doctor --debug` または
`--log-file` を使ってください。

## ログ出力

`git-ssh-sync` は、トラブルシューティングと同期操作の監視のための詳細なログ出力をサポートしています。

### ログレベル

デフォルトでは、警告とエラーのみが表示されます。以下のオプションで詳細度を上げることができます：

- `--verbose`, `-v`: INFO レベルのログを有効化（操作進捗、Git/SSH コマンド）
- `--debug`, `-d`: DEBUG レベルのログを有効化（全デバッグ情報、コマンド出力、スタックトレース）

### ログファイル出力

ログは自動的に `~/.cache/git-ssh-sync/logs/git-ssh-sync.log` に保存されます。ログファイルは、コンソール出力の設定に関係なく、すべてのログレベル（DEBUG 以上）を含みます。

`--log-file` でカスタムログファイルパスを指定できます：

```bash
git-ssh-sync pull myproject --log-file /tmp/my-sync.log
```

### 使用例

```bash
# デフォルト（警告とエラーのみ）
git-ssh-sync pull myproject

# 詳細出力（操作進捗）
git-ssh-sync pull myproject --verbose

# デバッグ出力（コマンド実行などの全詳細）
git-ssh-sync pull myproject --debug

# カスタムログファイル付き詳細出力
git-ssh-sync push myproject --verbose --log-file /tmp/sync.log

# 診断時のデバッグ出力
git-ssh-sync doctor myproject --debug
```

### ログ内容

- **INFO**: 操作進捗（pull/push/checkout）、成功メッセージ
- **DEBUG**: 実行された Git/SSH コマンド、戻り値、標準出力/標準エラー、作業ディレクトリ
- **WARNING**: 回復可能な問題（LFS、サブモジュール検出）
- **ERROR**: 失敗、実行エラー

ログは、SSH 接続の問題、Git コマンドの失敗、同期フローの理解などのトラブルシューティング時に特に役立ちます。

## 開発者向け

このリポジトリ自体を開発する場合は、依存関係を `uv sync` でインストールします。

```bash
uv sync
```

TestPyPI からインストールする場合:

```bash
uv tool install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  --index-strategy unsafe-best-match \
  git-ssh-sync
```

開発中に CLI を実行する場合は、`uv run` 経由で実行できます。

```bash
uv run git-ssh-sync --help
```

テストは次のコマンドで実行します。

```bash
uv run pytest
```

## 関連ドキュメント

- [仕様書](docs/spec.md)
