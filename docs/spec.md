# git-ssh-sync 仕様書 v0.1

## 1. 概要

`git-ssh-sync` は、GitHub / GitLab に直接アクセスできない開発環境で作成したGitコミットを、手元マシン経由で外部Gitサービスへ同期するためのCLIツールである。

このツールは **ファイル同期ツールではなく、Gitオブジェクト同期ツール** として設計する。

---

## 2. 名称

## 2.1 正式名称

```text
git-ssh-sync
```

## 2.2 コマンド名

```bash
git-ssh-sync
```

## 2.3 Gitサブコマンドとしての呼び出し

実行ファイル名を `git-ssh-sync` としてPATHに配置すると、Gitの外部サブコマンドとして以下のように呼び出せる。

```bash
git ssh-sync pull myproject
git ssh-sync push myproject
git ssh-sync status myproject
```

## 2.4 Pythonパッケージ名

```text
PyPI package: git-ssh-sync
Python module: git_ssh_sync
```

---

# 3. 目的

開発環境がGitHub / GitLabに直接アクセスできない場合でも、以下を可能にする。

```text
- GitHub / GitLabから取得した最新コミットを開発環境へ反映する
- 開発環境で作成したコミットをGitHub / GitLabへ反映する
- 開発環境にGitHub / GitLab用の認証情報を置かない
- 開発環境から外向き通信を行わない
- SSHポートフォワードを使わない
```

---

# 4. 前提環境

## 4.1 開発環境

```text
- 手元マシンからSSH / RDPで接続できる
- 開発環境から手元マシンへの接続は不可
- 開発環境からGitHub / GitLabへの接続は不可
- SSHポートフォワードによる迂回接続も不可
- gitコマンドは利用可能
- 実際の開発、編集、build、test、commitはこの環境で行う
```

## 4.2 手元マシン

```text
- GitHub / GitLabにアクセスできる
- gitコマンドを利用できる
- 開発環境へSSH接続できる
- git-ssh-sync は原則として手元マシン上で実行する
```

---

# 5. 基本思想

## 5.1 責務分離

```text
開発環境:
  - ソース編集
  - git add
  - git commit
  - git merge
  - git rebase
  - conflict解決
  - build / test

手元マシン:
  - GitHub / GitLabとのfetch / push
  - 開発環境へのSSH接続
  - 開発環境とのGitオブジェクト転送
  - 同期状態の確認
```

---

## 5.2 commitは開発環境で行う

`git-ssh-sync` は、MVPではcommit機能を持たない。

開発環境では通常どおり以下を実行する。

```bash
git status
git diff
git add .
git commit -m "message"
```

または、VSCode Remote SSH / RDP上のVSCode Source Controlからcommitする。

---

## 5.3 pull / pushは手元マシンから行う

GitHub / GitLabとの通信は手元マシンのみが担当する。

```bash
git-ssh-sync pull myproject
git-ssh-sync push myproject
```

---

## 5.4 未コミット変更は同期しない

MVPでは、開発環境の未コミットファイルを手元マシンへ同期しない。

理由：

```text
- ファイル同期ツール化を避ける
- .gitignore / symlink / permission / 改行コード / 削除検出の問題を避ける
- Gitの整合性をGit自身に任せる
- VSCode開発時の作業ディレクトリとcommit環境を一致させる
```

---

# 6. 全体アーキテクチャ

## 6.1 概要図

```text
GitHub / GitLab
    ↑↓
    │ fetch / push
    │
手元マシン
gateway repo
    ↑↓
    │ SSH
    │
開発環境
bare cache repo
    ↑↓
    │ local fetch
    │
work repo
```

---

## 6.2 手元マシン側リポジトリ

```text
~/.git-ssh-sync/repos/myproject/
```

これは通常のGitリポジトリ。

```text
origin -> GitHub / GitLab
dev    -> 開発環境 work repo
```

ただし、`dev` は直接push先としては使わず、主にfetch元として使う。

---

## 6.3 開発環境側リポジトリ

```text
~/.git-ssh-sync/cache/myproject.git   # bare repository
~/work/myproject                      # work repository
```

役割：

```text
bare cache repo:
  手元マシンからGitオブジェクトを受け取る中継用repo

work repo:
  VSCodeやRDPで実際に編集・commitするrepo
```

---

# 7. 同期方式

## 7.1 origin → 手元マシン → 開発環境

GitHub / GitLabの最新状態を開発環境へ反映する流れ。

```text
1. 手元マシンで origin から fetch
2. 手元マシンから開発環境の bare cache repo に push
3. 開発環境の work repo が bare cache repo から fetch
4. fast-forward可能なら作業ブランチを更新
```

---

## 7.2 開発環境 → 手元マシン → origin

開発環境で作成したcommitをGitHub / GitLabへ反映する流れ。

```text
1. 手元マシンから開発環境の work repo を fetch
2. 手元マシンの gateway repo に dev側ブランチを取り込む
3. origin側との差分・分岐状態を確認
4. 安全なら origin に push
```

---

# 8. コマンド一覧

MVPで提供するコマンド。

```text
git-ssh-sync init
git-ssh-sync clone
git-ssh-sync status
git-ssh-sync pull
git-ssh-sync push
git-ssh-sync checkout
git-ssh-sync doctor
```

Gitサブコマンド形式では以下。

```text
git ssh-sync init
git ssh-sync clone
git ssh-sync status
git ssh-sync pull
git ssh-sync push
git ssh-sync checkout
git ssh-sync doctor
```

---

# 9. コマンド仕様

## 9.1 `git-ssh-sync init`

プロジェクト設定を作成する。

### 使用例

```bash
git-ssh-sync init myproject
```

または：

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject \
  --branch main
```

### 処理内容

```text
1. 設定ファイルにproject情報を登録する
2. 手元マシン側のgateway repoパスを決定する
3. 開発環境側のwork repoパスを決定する
4. 開発環境側のbare cache repoパスを決定する
5. origin URLを保存する
6. default branchを保存する
```

---

## 9.2 `git-ssh-sync clone`

GitHub / GitLabから取得し、開発環境にも初期配置する。

### 使用例

```bash
git-ssh-sync clone myproject
```

### 処理内容

```text
1. 手元マシンにgateway repoをcloneする
2. 開発環境にbare cache repoを作成する
3. 手元マシンからbare cache repoへbranch / tagを転送する
4. 開発環境にwork repoを作成する
5. work repoでdefault branchをcheckoutする
6. work repoにcache repoをremoteとして登録する
```

### 内部処理イメージ

手元マシン：

```bash
git clone git@github.com:example/myproject.git ~/.git-ssh-sync/repos/myproject
git -C ~/.git-ssh-sync/repos/myproject fetch origin
```

開発環境：

```bash
git init --bare ~/.git-ssh-sync/cache/myproject.git
```

手元マシンから開発環境cache repoへ転送：

```bash
git -C ~/.git-ssh-sync/repos/myproject push \
  ssh://user@devserver/home/user/.git-ssh-sync/cache/myproject.git \
  refs/remotes/origin/main:refs/heads/main
```

開発環境：

```bash
git clone ~/.git-ssh-sync/cache/myproject.git ~/work/myproject
git -C ~/work/myproject remote rename origin gitsync
git -C ~/work/myproject switch main
```

---

## 9.3 `git-ssh-sync status`

origin、手元マシン、開発環境の差分状態を表示する。

### 使用例

```bash
git-ssh-sync status myproject
```

### 表示例

```text
Project: myproject

Origin:
  url: git@github.com:example/myproject.git
  branch: main
  head: a1b2c3d Update README

Development:
  host: devserver
  work path: /home/user/work/myproject
  branch: main
  head: d4e5f6a Add login feature
  working tree: clean

State:
  dev is ahead of origin by 2 commits
  origin is ahead of dev by 0 commits

Recommendation:
  git-ssh-sync push myproject
```

### チェック項目

```text
- originに接続できるか
- 開発環境にSSH接続できるか
- 開発環境のwork repoが存在するか
- 開発環境の現在branch
- 開発環境のworking treeがcleanか
- origin branchとdev branchのahead / behind
- Git LFS使用有無
- submodule使用有無
```

---

## 9.4 `git-ssh-sync pull`

GitHub / GitLabの最新状態を開発環境へ反映する。

### 使用例

```bash
git-ssh-sync pull myproject
```

branch指定：

```bash
git-ssh-sync pull myproject --branch main
```

### 処理内容

```text
1. 手元マシンでorigin fetchを実行する
2. origin branchを開発環境のbare cache repoへ転送する
3. 開発環境のwork repoでcache repoからfetchする
4. work repoの対象branchをfast-forward更新する
5. fast-forwardできない場合は停止する
```

### 安全ルール

`pull` はデフォルトで `fast-forward only` とする。

更新可能な状態：

```text
origin/main: A - B - C
dev/main:    A - B
```

更新不可の状態：

```text
origin/main: A - B - C
dev/main:    A - B - D
```

この場合は自動mergeしない。

### エラー例

```text
Cannot fast-forward main.

origin/main and dev/main have diverged.

Resolve on the development environment:

  git fetch gitsync
  git merge gitsync/main

or:

  git rebase gitsync/main
```

---

## 9.5 `git-ssh-sync push`

開発環境で作成したcommitをGitHub / GitLabへ反映する。

### 使用例

```bash
git-ssh-sync push myproject
```

branch指定：

```bash
git-ssh-sync push myproject --branch main
```

### 処理内容

```text
1. 手元マシンでorigin fetchを実行する
2. 手元マシンから開発環境work repoをfetchする
3. dev branchを手元マシンのrefs/remotes/dev/<branch>に取得する
4. origin branchとdev branchの関係を検査する
5. origin branchがdev branchの祖先ならpushする
6. 分岐していたら停止する
```

### 安全ルール

以下の場合のみpushする。

```text
origin/main が dev/main の祖先である
```

push可能な状態：

```text
origin/main: A - B
dev/main:    A - B - D
```

push不可の状態：

```text
origin/main: A - B - C
dev/main:    A - B - D
```

### エラー例

```text
Cannot push main.

origin/main has commits that are not included in dev/main.

Run:

  git-ssh-sync pull myproject

Then resolve merge or rebase on the development environment.
```

---

## 9.6 `git-ssh-sync checkout`

開発環境のwork repoでbranchを切り替える。

### 使用例

```bash
git-ssh-sync checkout myproject feature/foo
```

### 処理内容

```text
1. 手元マシンでorigin fetchを実行する
2. 指定branchがoriginに存在するか確認する
3. branchのGitオブジェクトを開発環境cache repoへ転送する
4. 開発環境work repoでfetchする
5. working treeがdirtyでないことを確認する
6. 開発環境work repoでgit switchする
```

### dirty時の挙動

開発環境のwork repoに未コミット変更がある場合は停止する。

```text
Working tree is dirty on the development environment.

Commit or stash changes first.
```

---

## 9.7 `git-ssh-sync doctor`

環境診断を行う。

### 使用例

```bash
git-ssh-sync doctor myproject
```

### チェック項目

手元マシン：

```text
- gitコマンドが存在する
- sshコマンドが存在する
- originへfetchできる
- originへpush可能か確認できる
- gateway repoが存在する
- gateway repoが破損していない
```

開発環境：

```text
- SSH接続できる
- gitコマンドが存在する
- bare cache repoが存在する
- work repoが存在する
- work repoのbranchを取得できる
- working treeの状態を取得できる
```

リポジトリ：

```text
- Git LFSを使っていないか
- submoduleを使っていないか
- default branchが存在するか
- originとdevの履歴が接続しているか
```

---

# 10. 設定ファイル仕様

## 10.1 配置場所

Linux / macOS：

```text
~/.config/git-ssh-sync/config.yaml
```

Windows：

```text
%APPDATA%\git-ssh-sync\config.yaml
```

---

## 10.2 設定例

```yaml
version: 1

projects:
  myproject:
    origin: git@github.com:example/myproject.git
    default_branch: main

    local:
      repo_path: ~/.git-ssh-sync/repos/myproject

    dev:
      host: devserver
      user: user
      work_path: /home/user/work/myproject
      cache_path: /home/user/.git-ssh-sync/cache/myproject.git

    options:
      sync_tags: true
      lfs: false
      submodules: false
      ff_only: true
```

---

# 11. 内部ref設計

## 11.1 手元マシン gateway repo

```text
refs/remotes/origin/<branch>
refs/remotes/dev/<branch>
```

例：

```text
refs/remotes/origin/main
refs/remotes/dev/main
```

---

## 11.2 開発環境 bare cache repo

```text
refs/heads/<branch>
refs/tags/*
```

例：

```text
refs/heads/main
refs/heads/feature/foo
```

---

## 11.3 開発環境 work repo

```text
refs/heads/<branch>
refs/remotes/gitsync/<branch>
```

work repoのremote名は `gitsync` とする。

```bash
git remote add gitsync /home/user/.git-ssh-sync/cache/myproject.git
```

---

# 12. 状態判定ロジック

## 12.1 ahead / behind判定

手元マシンで以下を使う。

```bash
git rev-list --left-right --count origin/main...dev/main
```

結果：

```text
<left> <right>
```

意味：

```text
left  = originにだけあるcommit数
right = devにだけあるcommit数
```

---

## 12.2 pull可能判定

```bash
git merge-base --is-ancestor dev/main origin/main
```

この判定が成功する場合のみ、開発環境側でfast-forwardする。

---

## 12.3 push可能判定

```bash
git merge-base --is-ancestor origin/main dev/main
```

この判定が成功する場合のみ、originへpushする。

---

# 13. エラー方針

## 13.1 自動で行わない操作

MVPでは以下を自動実行しない。

```text
- merge commitの作成
- rebase
- conflict解決
- force push
- 未コミット変更のstash
- 未コミット変更の破棄
- checked-out branchへの外部push
```

---

## 13.2 エラー時の表示方針

エラー時は以下を表示する。

```text
- 何が起きたか
- どの環境で起きたか
- 現在のbranch / commit
- ユーザーが次に実行すべきコマンド
```

例：

```text
Error: Development working tree is dirty.

Project:
  myproject

Development:
  host: devserver
  path: /home/user/work/myproject
  branch: main

Next action:
  Commit or stash changes on the development environment.
```

---

# 14. Git LFS対応方針

MVPではGit LFSを完全対応しない。

## 14.1 検出方法

```bash
git lfs ls-files
```

または `.gitattributes` を確認する。

## 14.2 検出時の警告

```text
This repository appears to use Git LFS.

Git LFS object synchronization is not supported in v0.1.
Normal Git commits may sync, but LFS file contents may be missing.
```

---

# 15. submodule対応方針

MVPではsubmoduleを完全対応しない。

## 15.1 検出方法

```bash
test -f .gitmodules
```

## 15.2 検出時の警告

```text
This repository uses Git submodules.

Submodule synchronization is not supported in v0.1.
Register each submodule as a separate git-ssh-sync project.
```

---

# 16. 技術スタック

## 16.1 言語

```text
Python 3.12+
```

---

## 16.2 推奨ライブラリ

```text
Typer       CLIフレームワーク
Rich        見やすいログ・テーブル表示
PyYAML      config.yaml読み書き
Pydantic    設定バリデーション
```

最小構成にする場合：

```text
argparse
subprocess
pathlib
dataclasses
yaml
```

---

## 16.3 Git操作方針

Git操作はGitPythonではなく、原則として `subprocess` で `git` コマンドを直接呼び出す。

理由：

```text
- git CLIの挙動をそのまま使える
- エラー原因を追いやすい
- SSH経由のGit操作と相性がよい
- GitPython固有の抽象化を避けられる
```

---

# 17. Pythonパッケージ構成案

```text
git_ssh_sync/
  __init__.py
  cli.py
  config.py
  git.py
  ssh.py
  project.py
  sync.py
  status.py
  doctor.py
  errors.py
```

---

## 17.1 `cli.py`

TyperによるCLIエントリポイント。

担当：

```text
- init
- clone
- status
- pull
- push
- checkout
- doctor
```

---

## 17.2 `config.py`

設定ファイル管理。

担当：

```text
- config.yamlの読み込み
- config.yamlの保存
- project設定の取得
- path展開
- バリデーション
```

---

## 17.3 `git.py`

ローカルGitコマンド実行。

担当：

```text
- git fetch
- git push
- git rev-parse
- git status --porcelain
- git merge-base
- git rev-list
- git remote
```

---

## 17.4 `ssh.py`

SSH越しのコマンド実行。

担当：

```text
- ssh host command
- remote git command
- remote path作成
- remote repo存在確認
- remote working tree状態確認
```

---

## 17.5 `sync.py`

同期処理本体。

担当：

```text
- pull_origin_to_dev
- push_dev_to_origin
- transfer_branch_to_dev_cache
- fetch_dev_branch_to_local
```

---

## 17.6 `doctor.py`

環境診断。

担当：

```text
- check_local_git
- check_local_ssh
- check_origin_access
- check_dev_ssh
- check_dev_git
- check_repo_layout
```

---

# 18. ログ設計

通常表示：

```text
[local] fetching origin/main
[dev] updating cache repo
[dev] fetching into work repo
[dev] fast-forwarding main
Done.
```

詳細表示：

```bash
git-ssh-sync pull myproject --verbose
```

詳細表示時は実行コマンドも表示する。

```text
$ git -C ~/.git-ssh-sync/repos/myproject fetch origin
$ git -C ~/.git-ssh-sync/repos/myproject push ssh://...
$ ssh devserver 'git -C /home/user/work/myproject fetch gitsync'
```

---

# 19. セキュリティ方針

```text
- GitHub / GitLabの認証情報は手元マシンにのみ置く
- 開発環境にはGitHub / GitLabのtokenやSSH keyを置かない
- 開発環境から外向き通信を発生させない
- SSHポートフォワードは使わない
- CLIは手元マシンから開発環境へSSH接続するだけ
```

---

# 20. 標準ワークフロー

## 20.1 初回

```bash
git-ssh-sync init myproject
git-ssh-sync clone myproject
git-ssh-sync doctor myproject
```

---

## 20.2 日常開発

手元マシン：

```bash
git-ssh-sync pull myproject
```

開発環境：

```bash
cd ~/work/myproject
git status
git add .
git commit -m "Add feature"
```

手元マシン：

```bash
git-ssh-sync push myproject
```

---

## 20.3 ブランチ切り替え

手元マシン：

```bash
git-ssh-sync checkout myproject feature/foo
```

開発環境：

```bash
git status
git add .
git commit -m "Implement foo"
```

手元マシン：

```bash
git-ssh-sync push myproject --branch feature/foo
```

---

# 21. MVP実装範囲

## v0.1

```text
- config.yaml対応
- init
- clone
- status
- pull
- push
- checkout
- doctor
- fast-forward only
- dirty working tree検出
- Git LFS検出と警告
- submodule検出と警告
- Richによる見やすい出力
```

---

# 22. 将来拡張

## v0.2

```text
- 複数branchの一括同期
- tag同期の強化
- dry-run
- prune
- verboseログ
- remote command補助
  - git-ssh-sync dev status
  - git-ssh-sync dev diff
  - git-ssh-sync dev log
```

## v0.3

```text
- Git LFS同期
- submodule同期
- hook機能
- VSCode連携補助
- 複数開発環境対応
- bundle backend対応
```

---

# 23. 重要な設計判断

## 23.1 採用する方針

```text
- commitは開発環境で行う
- GitHub / GitLabとの通信は手元マシンで行う
- 開発環境との通信はSSHのみ
- 同期対象はコミット済みGitオブジェクト
- pull / pushは安全確認後に実行
- 自動merge / 自動rebaseはしない
```

---

## 23.2 採用しない方針

```text
- 開発環境の未コミット変更を手元マシンへ同期してcommitする
- 開発環境にGitHub / GitLab認証情報を置く
- SSHポートフォワードで外部Gitサービスへ接続する
- 作業中branchへ外部から直接pushする
- dirty working treeを自動stashする
```

---

# 24. 一文での説明

```text
git-ssh-sync は、GitHub / GitLabに直接アクセスできない開発環境のために、
手元マシンをGitゲートウェイとして使い、SSH経由でコミット済みGitオブジェクトを同期するCLIである。
```

または短く言うなら：

```text
GitHub / GitLabに繋がらない開発環境でも、手元マシン経由で安全にpull / pushできるGit同期CLI。
```
