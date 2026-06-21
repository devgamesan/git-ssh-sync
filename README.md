# git-ssh-sync

[![CI](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Release](https://img.shields.io/github/v/release/devgamesan/git-ssh-sync)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`git-ssh-sync` は、GitHub / GitLab に直接アクセスできない開発環境で作成した Git コミットを、手元マシン経由で外部 Git サービスへ同期するための CLI ツールです。

このツールはファイル同期ツールではありません。同期するのは Git オブジェクトとブランチです。ソース編集、ビルド、テスト、コミットは開発環境で行い、GitHub / GitLab との通信は手元マシンで行います。

## 前提

`git-ssh-sync` は次のような構成を前提にしています。

```text
GitHub / GitLab
    ↑↓
手元マシン
    ↑↓ SSH
開発環境
```

手元マシン:

- GitHub / GitLab にアクセスできる
- 開発環境へ SSH 接続できる
- `git` と `uv` を利用できる
- `git-ssh-sync` を実行する

開発環境:

- 手元マシンから SSH 接続できる
- `git` を利用できる
- ソース編集、ビルド、テスト、コミットを行う
- GitHub / GitLab の認証情報を置かない

## 環境構築

依存関係は `uv sync` でインストールします。

```bash
uv sync
```

開発中に CLI を実行する場合は、`uv run` 経由で実行します。

```bash
uv run git-ssh-sync --help
```

テストは次のコマンドで実行します。

```bash
uv run pytest
```

## 設定

最初に、同期したいプロジェクトを登録します。

```bash
uv run git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject \
  --branch main
```

主な指定内容は次のとおりです。

- `myproject`: `git-ssh-sync` 上のプロジェクト名
- `--origin`: GitHub / GitLab 側のリポジトリ URL
- `--dev-host`: 開発環境の SSH ホスト
- `--dev-user`: 開発環境の SSH ユーザー
- `--dev-path`: 開発環境上の work repo パス
- `--branch`: 既定で同期するブランチ

登録済みの設定を上書きする場合は `--force` を付けます。

```bash
uv run git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject \
  --branch main \
  --force
```

## 初回 workflow

初回は、設定作成、開発環境への clone、診断の順に実行します。

```bash
uv run git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject \
  --branch main
uv run git-ssh-sync clone myproject
uv run git-ssh-sync doctor myproject
```

`clone` は手元マシンに gateway repo を作成し、開発環境に cache repo と work repo を配置します。以後、開発環境では通常の Git リポジトリとして作業できます。

`doctor` はローカル環境、SSH 接続、origin への fetch / push 権限、開発環境側のリポジトリ配置を確認します。初回だけでなく、同期がうまくいかない時にも最初に実行してください。

## 日常開発 workflow

日常開発では、作業開始前に手元マシンから `pull` し、開発環境で通常どおりコミットし、最後に手元マシンから `push` します。

手元マシン:

```bash
uv run git-ssh-sync pull myproject --branch main
```

開発環境:

```bash
cd ~/work/myproject
git status
git add .
git commit -m "Add feature"
```

手元マシン:

```bash
uv run git-ssh-sync push myproject --branch main
```

`pull` と `push` は対象ブランチを明示する必要があります。

```bash
uv run git-ssh-sync pull myproject --branch main
uv run git-ssh-sync push myproject --branch main
```

## ブランチ切り替え workflow

既存ブランチへ切り替える場合は、手元マシンから `checkout` を実行します。

手元マシン:

```bash
uv run git-ssh-sync checkout myproject feature/foo
```

新しいブランチを指定したベースブランチから作る場合は `--base` を付けます。

```bash
uv run git-ssh-sync checkout myproject feature/foo --base develop
```

開発環境:

```bash
cd ~/work/myproject
git status
git add .
git commit -m "Implement foo"
```

手元マシン:

```bash
uv run git-ssh-sync push myproject --branch feature/foo
```

`checkout --base develop` は、origin の `develop` を元に `feature/foo` を作成し、開発環境の work repo をそのブランチへ切り替えます。すでに origin に同名ブランチがある場合は、`--base` なしで既存ブランチへ切り替えてください。

## 状態確認

同期状態を確認するには `status` を使います。

```bash
uv run git-ssh-sync status myproject
```

`status` は origin、手元マシン、開発環境のブランチと ahead / behind の状態を表示します。表示された recommendation に従って、必要に応じて `pull` または `push` を実行してください。

## 運用ルール

`git-ssh-sync` を使う時は、次のルールを守ると状態を把握しやすくなります。

- 作業開始前に手元マシンで `pull` する
- コミットは開発環境で作る
- 作業が終わったら手元マシンで `push` する
- 同期前後で迷ったら `status` を見る
- 接続やリポジトリ配置に不安がある時は `doctor` を実行する

未コミット変更は同期されません。開発環境の作業ツリーに未コミットの変更がある場合、その変更自体は手元マシンや origin には送られません。同期したい変更は、開発環境で `git add` と `git commit` を済ませてください。

`pull` は fast-forward できる場合だけ開発環境のブランチを更新します。origin と開発環境が分岐している場合、自動 merge や自動 rebase は行いません。

`push` は origin 側のブランチが開発環境側のブランチの祖先である場合だけ実行します。origin に未取得のコミットがある場合は停止します。

分岐した場合は、先に手元マシンで `pull` を実行し、開発環境で merge または rebase を行ってから、再度 `push` してください。

## よく使うコマンド

```bash
# ヘルプを表示
uv run git-ssh-sync --help

# プロジェクトを登録
uv run git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject \
  --branch main

# 初回 clone
uv run git-ssh-sync clone myproject

# 同期状態を確認
uv run git-ssh-sync status myproject

# origin の変更を開発環境へ反映
uv run git-ssh-sync pull myproject --branch main

# 開発環境のコミットを origin へ反映
uv run git-ssh-sync push myproject --branch main

# 開発環境のブランチを切り替え
uv run git-ssh-sync checkout myproject feature/foo

# ベースブランチから新規ブランチを作成して切り替え
uv run git-ssh-sync checkout myproject feature/foo --base develop

# 診断
uv run git-ssh-sync doctor myproject

# テスト
uv run pytest
```

## Git サブコマンドとして使う場合

`git-ssh-sync` が `PATH` にある場合は、Git の外部サブコマンドとしても呼び出せます。

```bash
git ssh-sync pull myproject --branch main
git ssh-sync push myproject --branch main
git ssh-sync status myproject
```

開発中は `uv run git-ssh-sync ...` を使うのが確実です。

## 関連ドキュメント

- [仕様書](docs/spec.md)
