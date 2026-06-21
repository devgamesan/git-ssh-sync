# git-ssh-sync

[![CI](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Release](https://img.shields.io/github/v/release/devgamesan/git-ssh-sync)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`git-ssh-sync` は、GitHub / GitLab に直接アクセスできない開発環境で作成した Git コミットを、ローカルマシン経由で外部 Git サービスへ同期するための CLI ツールです。

このツールはファイル同期ツールではありません。同期するのは Git オブジェクトとブランチです。ソース編集、ビルド、テスト、コミットは開発環境で行い、GitHub / GitLab との通信はローカルマシンで行います。

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
- `--dev-path`: 開発環境上の work repo パス

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

`clone` はローカルマシンに gateway repo を作成し、開発環境に cache repo と work repo を配置します。

- gateway repo: ローカルマシン上にある中継用リポジトリ
- cache repo: 開発環境上にある bare リポジトリ
- work repo: 開発環境上で実際に編集、ビルド、テスト、コミットを行うリポジトリ

以後、開発環境では work repo を通常の Git リポジトリとして扱えます。

`doctor` はローカル環境、SSH 接続、origin への fetch / push 権限、開発環境側のリポジトリ配置を確認します。初回だけでなく、同期がうまくいかない時にも最初に実行してください。

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

分岐した場合は自動では解決しません。ローカルマシンで `pull` を実行して表示された手順に従い、開発環境で merge または rebase を行ってから、再度 `push` してください。

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

# 初回 clone
git-ssh-sync clone myproject

# 同期状態を確認
git-ssh-sync status myproject

# ブランチ状態を確認
git-ssh-sync branch myproject

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
```

## 開発者向け

このリポジトリ自体を開発する場合は、依存関係を `uv sync` でインストールします。

```bash
uv sync
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
