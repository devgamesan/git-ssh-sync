# 手動テストチェックリスト

この文書は、`git-ssh-sync` の主要な利用フローを実環境で確認するための手動テストチェックリストです。

ローカルマシンは macOS / Linux などの POSIX 環境を前提にします。リモート開発環境は Linux と Windows の 2 パターンを確認します。

## 自動実行

チェックリストの主要フローは、CI には組み込まず、手動 E2E テストとして実行できます。テストは `manual_tests/` に置いているため、通常の `uv run pytest` では実行されません。

実行には、テスト用 origin リポジトリと、SSH 接続可能な Linux または Windows リモート環境が必要です。origin リポジトリには一時ブランチを作成して削除します。リモート環境には一時 work repo と cache repo を作成して削除します。

origin へのアクセスには、ローカルマシンの `git` が通常使用している認証情報を使います。HTTPS の private repository を使う場合は credential helper、SSH URL を使う場合は SSH key など、非対話で `git clone` / `git fetch` / `git push` できる状態にしてください。テスト中の `git-ssh-sync` 設定ファイルは `XDG_CONFIG_HOME` を一時ディレクトリへ向けて隔離しますが、`HOME` は変更しないため、ローカルの Git 認証設定はそのまま使われます。

Linux リモートだけで実行する例:

```bash
GSS_TEST_ORIGIN_URL=git@github.com:example/manual-test-origin.git \
GSS_TEST_LINUX_HOST=linux.example.com \
GSS_TEST_LINUX_USER=devuser \
uv run pytest manual_tests
```

Windows リモートだけで実行する例:

```bash
GSS_TEST_ORIGIN_URL=git@github.com:example/manual-test-origin.git \
GSS_TEST_WINDOWS_HOST=windows.example.com \
GSS_TEST_WINDOWS_USER=devuser \
uv run pytest manual_tests
```

Linux と Windows の両方を同時に指定すると、両方のリモートに対して同じフローを実行します。

任意で次の環境変数を指定できます。

```text
GSS_CLI_COMMAND              実行する CLI コマンド。既定値は "uv run git-ssh-sync"
GSS_TEST_BASE_BRANCH         origin の既定ブランチを検出できない場合の base branch。既定値は main
GSS_TEST_LINUX_PROJECT       Linux 用 project 名
GSS_TEST_LINUX_WORK_PATH     Linux リモートの work repo パス
GSS_TEST_LINUX_CACHE_PATH    Linux リモートの cache repo パス
GSS_TEST_WINDOWS_PROJECT     Windows 用 project 名
GSS_TEST_WINDOWS_WORK_PATH   Windows リモートの work repo パス
GSS_TEST_WINDOWS_CACHE_PATH  Windows リモートの cache repo パス
```

## テスト前提

### 環境

- [ ] ローカルマシンで `git` が実行できる
- [ ] ローカルマシンで `uv` が実行できる
- [ ] ローカルマシンで `uv run git-ssh-sync --help` またはインストール済みの `git-ssh-sync --help` が実行できる
- [ ] ローカルマシンから Linux リモートへ SSH 接続できる
- [ ] ローカルマシンから Windows リモートへ SSH 接続できる
- [ ] Linux リモートで `git` が実行できる
- [ ] Windows リモートで `git` が実行できる
- [ ] テスト用 origin リポジトリを用意している
- [ ] origin リポジトリにローカルマシンから fetch / push できる

### プレースホルダー

以降の手順では、次の値を自分の環境に置き換えます。

```text
<origin-url>          テスト用 origin リポジトリ URL
<linux-host>          Linux リモート SSH ホスト
<linux-user>          Linux リモート SSH ユーザー
<windows-host>        Windows リモート SSH ホスト
<windows-user>        Windows リモート SSH ユーザー
<linux-project>       Linux リモート用の git-ssh-sync プロジェクト名
<windows-project>     Windows リモート用の git-ssh-sync プロジェクト名
```

推奨例:

```text
<linux-project>       manual-linux
<windows-project>     manual-windows
```

### 作業パス

Linux リモート:

```text
/home/<linux-user>/work/git-ssh-sync-manual
```

Windows リモート:

```text
C:\Users\<windows-user>\work\git-ssh-sync-manual
```

POSIX シェルから Windows パスを渡す場合は、バックスラッシュが削除されないように必ず引用します。

```bash
--dev-path 'C:\Users\<windows-user>\work\git-ssh-sync-manual'
```

## 共通準備

### 設定ファイル退避

目的: 既存の `git-ssh-sync` 設定を壊さずに手動テストを実施できることを確認する。

対象リモート: 共通

前提:

- ローカルマシンで POSIX シェルを使っている

手順:

```bash
mkdir -p ~/.config/git-ssh-sync
if [ -f ~/.config/git-ssh-sync/config.yaml ]; then
  cp ~/.config/git-ssh-sync/config.yaml ~/.config/git-ssh-sync/config.yaml.manual-test.bak
fi
```

期待結果:

- [ ] 既存の設定ファイルがある場合、バックアップを作成できる
- [ ] 既存の設定ファイルがない場合、コマンドが失敗しない

後片付け:

- テスト完了後、「後片付け」の章に従って復元する

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### CLI 起動確認

目的: ローカルマシンから CLI を実行できることを確認する。

対象リモート: 共通

前提:

- 開発中のリポジトリで実行する場合は、このリポジトリのルートにいる

手順:

```bash
uv run git-ssh-sync --help
uv run git-ssh-sync --version
```

期待結果:

- [ ] `--help` がコマンド一覧を表示する
- [ ] `--version` がバージョンを表示する
- [ ] どちらも終了コード 0 で完了する

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

## 設定管理

### Linux リモート用プロジェクト登録

目的: Linux リモート向けの設定を作成できることを確認する。

対象リモート: Linux

前提:

- `<origin-url>`、`<linux-host>`、`<linux-user>` が決まっている

手順:

```bash
uv run git-ssh-sync init <linux-project> \
  --origin <origin-url> \
  --dev-host <linux-host> \
  --dev-user <linux-user> \
  --dev-os posix \
  --dev-path /home/<linux-user>/work/git-ssh-sync-manual

uv run git-ssh-sync config show <linux-project>
```

期待結果:

- [ ] 設定保存メッセージが表示される
- [ ] `dev os` が `posix` になる
- [ ] `dev path` が指定した Linux パスになる
- [ ] `dev cache_path` が `/home/<linux-user>/.git-ssh-sync/cache/<linux-project>.git` になる

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### Windows リモート用プロジェクト登録

目的: Windows リモート向けの設定を作成できることを確認する。

対象リモート: Windows

前提:

- `<origin-url>`、`<windows-host>`、`<windows-user>` が決まっている

手順:

```bash
uv run git-ssh-sync init <windows-project> \
  --origin <origin-url> \
  --dev-host <windows-host> \
  --dev-user <windows-user> \
  --dev-os windows \
  --dev-path 'C:\Users\<windows-user>\work\git-ssh-sync-manual'

uv run git-ssh-sync config show <windows-project>
```

期待結果:

- [ ] 設定保存メッセージが表示される
- [ ] `dev os` が `windows` になる
- [ ] `dev path` が指定した Windows パスになる
- [ ] `dev cache_path` が `C:\Users\<windows-user>\.git-ssh-sync\cache\<windows-project>.git` になる
- [ ] POSIX シェルでバックスラッシュが失われていない

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### 設定一覧と更新

目的: 登録済み設定を一覧表示し、個別項目を更新できることを確認する。

対象リモート: 共通

前提:

- Linux と Windows のプロジェクト登録が完了している

手順:

```bash
uv run git-ssh-sync config list

uv run git-ssh-sync config set <linux-project> --no-sync-tags --ff-only
uv run git-ssh-sync config show <linux-project>

uv run git-ssh-sync config set <linux-project> --sync-tags
uv run git-ssh-sync config show <linux-project>
```

期待結果:

- [ ] `config list` に両方のプロジェクトが表示される
- [ ] `--no-sync-tags` 後に `sync_tags` が `False` になる
- [ ] `--sync-tags` 後に `sync_tags` が `True` に戻る
- [ ] `ff_only` が `True` のままになる

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### 既存設定の上書き

目的: `init` が既存設定を誤って上書きせず、`--force` 指定時だけ上書きすることを確認する。

対象リモート: Linux

前提:

- `<linux-project>` が登録済み

手順:

```bash
uv run git-ssh-sync init <linux-project> \
  --origin <origin-url> \
  --dev-host <linux-host> \
  --dev-user <linux-user> \
  --dev-os posix \
  --dev-path /home/<linux-user>/work/git-ssh-sync-manual

uv run git-ssh-sync init <linux-project> \
  --origin <origin-url> \
  --dev-host <linux-host> \
  --dev-user <linux-user> \
  --dev-os posix \
  --dev-path /home/<linux-user>/work/git-ssh-sync-manual \
  --force
```

期待結果:

- [ ] 1 回目は既存プロジェクトのエラーで終了コード 1 になる
- [ ] `--force` 付きは成功する
- [ ] 設定内容が壊れていない

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

## 初回導入

### Linux リモートへの clone

目的: Linux リモートに cache repo と work repo を作成できることを確認する。

対象リモート: Linux

前提:

- `<linux-project>` が登録済み
- Linux リモートの work path と cache path が存在しない

手順:

```bash
uv run git-ssh-sync clone <linux-project>
uv run git-ssh-sync doctor <linux-project>
ssh <linux-user>@<linux-host> 'git -C /home/<linux-user>/work/git-ssh-sync-manual status --short --branch'
ssh <linux-user>@<linux-host> 'git -C /home/<linux-user>/work/git-ssh-sync-manual remote -v'
```

期待結果:

- [ ] `clone` が成功する
- [ ] `doctor` が成功する
- [ ] Linux リモートの work repo が通常の Git リポジトリとして使える
- [ ] work repo に `gitsync` remote が存在する
- [ ] ローカル gateway repo が `~/.git-ssh-sync/repos/<linux-project>` に作成される

後片付け:

- 続くテストで利用するため削除しない

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### Windows リモートへの clone

目的: Windows リモートに cache repo と work repo を作成できることを確認する。

対象リモート: Windows

前提:

- `<windows-project>` が登録済み
- Windows リモートの work path と cache path が存在しない

手順:

```bash
uv run git-ssh-sync clone <windows-project>
uv run git-ssh-sync doctor <windows-project>
ssh <windows-user>@<windows-host> "powershell -NoProfile -Command \"git -C 'C:\Users\<windows-user>\work\git-ssh-sync-manual' status --short --branch\""
ssh <windows-user>@<windows-host> "powershell -NoProfile -Command \"git -C 'C:\Users\<windows-user>\work\git-ssh-sync-manual' remote -v\""
```

期待結果:

- [ ] `clone` が成功する
- [ ] `doctor` が成功する
- [ ] Windows リモートの work repo が通常の Git リポジトリとして使える
- [ ] work repo に `gitsync` remote が存在する
- [ ] ローカル gateway repo が `~/.git-ssh-sync/repos/<windows-project>` に作成される

後片付け:

- 続くテストで利用するため削除しない

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

## 状態確認と参照用コマンド

### status と branch

目的: origin、gateway、リモートwork repoの同期状態を確認できることを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している

手順:

```bash
uv run git-ssh-sync status <project>
uv run git-ssh-sync branch <project>
```

期待結果:

- [ ] `status` がリモートwork repoのカレントブランチを表示する
- [ ] `status` が ahead / behind と recommendation を表示する
- [ ] `branch` が origin / cache / work repo のブランチ状態を表示する
- [ ] 終了コード 0 で完了する

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

### dev status / diff / log

目的: ローカルマシンからリモートwork repoの状態を参照できることを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している

手順:

```bash
uv run git-ssh-sync dev status <project>
uv run git-ssh-sync dev diff <project>
uv run git-ssh-sync dev diff <project> --stat
uv run git-ssh-sync dev diff <project> --cached
uv run git-ssh-sync dev log <project> --max-count 5
```

期待結果:

- [ ] `dev status` が `git status --short --branch` 相当を表示する
- [ ] `dev diff` が未コミット差分を表示する
- [ ] `dev diff --stat` が差分統計を表示する
- [ ] `dev diff --cached` がステージ済み差分を表示する
- [ ] `dev log --max-count 5` が最大 5 件のログを表示する
- [ ] origin、gateway、cache、work repo の ref を変更しない

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

## 日常同期

### origin からリモートへ pull

目的: origin の新しいコミットをリモートwork repoへ fast-forward できることを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している
- origin 側にリモートwork repoへ未反映のコミットを 1 つ追加できる

手順:

```bash
git clone <origin-url> /tmp/git-ssh-sync-origin-edit
cd /tmp/git-ssh-sync-origin-edit
printf "origin update\n" >> manual-test.txt
git add manual-test.txt
git commit -m "Add origin manual test update"
git push origin HEAD
cd -

uv run git-ssh-sync pull <project> --dry-run
uv run git-ssh-sync pull <project>
uv run git-ssh-sync status <project>
```

期待結果:

- [ ] `pull --dry-run` が変更予定の操作を表示し、refを変更しない
- [ ] `pull` が成功する
- [ ] リモートwork repoに origin 側のコミットが反映される
- [ ] `status` が同期済み、または期待どおりの ahead / behind を表示する

後片付け:

```bash
rm -rf /tmp/git-ssh-sync-origin-edit
```

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

### リモートから origin へ push

目的: リモートwork repoで作成したコミットを origin へ push できることを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している
- リモートwork repoが clean である

手順:

Linux リモート:

```bash
ssh <linux-user>@<linux-host> '
  cd /home/<linux-user>/work/git-ssh-sync-manual &&
  printf "linux remote update\n" >> manual-test.txt &&
  git add manual-test.txt &&
  git commit -m "Add Linux remote manual test update"
'
uv run git-ssh-sync push <linux-project> --dry-run
uv run git-ssh-sync push <linux-project>
```

Windows リモート:

```bash
ssh <windows-user>@<windows-host> "powershell -NoProfile -Command \"Set-Location 'C:\Users\<windows-user>\work\git-ssh-sync-manual'; Add-Content -Path manual-test.txt -Value 'windows remote update'; git add manual-test.txt; git commit -m 'Add Windows remote manual test update'\""
uv run git-ssh-sync push <windows-project> --dry-run
uv run git-ssh-sync push <windows-project>
```

共通確認:

```bash
git clone <origin-url> /tmp/git-ssh-sync-origin-check
git -C /tmp/git-ssh-sync-origin-check log --oneline --max-count 5
```

期待結果:

- [ ] `push --dry-run` が変更予定の操作を表示し、refを変更しない
- [ ] `push` が成功する
- [ ] origin にリモート側のコミットが反映される
- [ ] リモートwork repoの未コミット変更は残らない

後片付け:

```bash
rm -rf /tmp/git-ssh-sync-origin-check
```

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### dirty work tree の確認

目的: リモートwork repoに未コミット変更がある場合、参照コマンドで状態を把握できることを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している
- リモートwork repoが clean である

手順:

Linux リモート:

```bash
ssh <linux-user>@<linux-host> '
  cd /home/<linux-user>/work/git-ssh-sync-manual &&
  printf "dirty linux\n" >> dirty.txt
'
uv run git-ssh-sync dev status <linux-project>
uv run git-ssh-sync dev diff <linux-project> --stat
```

Windows リモート:

```bash
ssh <windows-user>@<windows-host> "powershell -NoProfile -Command \"Set-Location 'C:\Users\<windows-user>\work\git-ssh-sync-manual'; Add-Content -Path dirty.txt -Value 'dirty windows'\""
uv run git-ssh-sync dev status <windows-project>
uv run git-ssh-sync dev diff <windows-project> --stat
```

期待結果:

- [ ] `dev status` が未コミット変更を表示する
- [ ] `dev diff --stat` が差分統計を表示する
- [ ] 未コミット変更そのものは origin に送られない

後片付け:

Linux リモート:

```bash
ssh <linux-user>@<linux-host> '
  cd /home/<linux-user>/work/git-ssh-sync-manual &&
  git checkout -- dirty.txt 2>/dev/null || rm -f dirty.txt
'
```

Windows リモート:

```bash
ssh <windows-user>@<windows-host> "powershell -NoProfile -Command \"Set-Location 'C:\Users\<windows-user>\work\git-ssh-sync-manual'; git checkout -- dirty.txt 2>\$null; if (Test-Path dirty.txt) { Remove-Item dirty.txt }\""
```

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

## 分岐と停止条件

### origin 先行時の push 停止

目的: origin に未取得コミットがある場合、`push` が安全に停止することを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している
- リモートwork repoが clean である

手順:

```bash
git clone <origin-url> /tmp/git-ssh-sync-origin-ahead
cd /tmp/git-ssh-sync-origin-ahead
printf "origin ahead\n" >> manual-test.txt
git add manual-test.txt
git commit -m "Add origin ahead update"
git push origin HEAD
cd -

uv run git-ssh-sync push <project>
```

期待結果:

- [ ] `push` が終了コード 1 で停止する
- [ ] origin に未取得コミットがある旨のエラーが表示される
- [ ] `pull` してから解決する案内が表示される
- [ ] origin とリモートwork repoの履歴を壊さない

後片付け:

```bash
rm -rf /tmp/git-ssh-sync-origin-ahead
uv run git-ssh-sync pull <project>
```

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

### origin とリモートの分岐

目的: origin とリモートwork repoが分岐した場合、自動merge/rebaseせず停止することを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している
- リモートwork repoが clean である

手順:

1. origin 側でコミットを追加して push する。
2. `pull` せずに、リモートwork repoでも別コミットを追加する。
3. ローカルマシンで次を実行する。

```bash
uv run git-ssh-sync push <project>
uv run git-ssh-sync pull <project>
```

期待結果:

- [ ] `push` が origin 先行を検出して停止する
- [ ] `pull` が fast-forward できない場合に停止する
- [ ] 自動mergeや自動rebaseを行わない
- [ ] リモート環境で `git fetch gitsync` と merge/rebase を行う案内が表示される

後片付け:

- リモートwork repoで通常の Git 操作として merge または rebase を完了する
- 解決後に `uv run git-ssh-sync push <project>` を実行する

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

## ブランチ操作

### 既存ブランチへの checkout

目的: origin に存在するブランチへリモートwork repoを切り替えられることを確認する。

対象リモート: Linux / Windows

前提:

- origin に `manual/existing` ブランチを作成できる
- リモートwork repoが clean である

手順:

```bash
git clone <origin-url> /tmp/git-ssh-sync-branch-edit
cd /tmp/git-ssh-sync-branch-edit
git switch -c manual/existing
printf "existing branch\n" >> branch-test.txt
git add branch-test.txt
git commit -m "Add existing branch manual test"
git push origin manual/existing
cd -

uv run git-ssh-sync checkout <project> manual/existing --dry-run
uv run git-ssh-sync checkout <project> manual/existing
uv run git-ssh-sync status <project>
```

期待結果:

- [ ] `checkout --dry-run` が変更予定の操作を表示し、refやブランチを変更しない
- [ ] `checkout` が成功する
- [ ] リモートwork repoのカレントブランチが `manual/existing` になる

後片付け:

```bash
rm -rf /tmp/git-ssh-sync-branch-edit
```

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

### 新規ブランチ作成

目的: `checkout -b` で origin 上に新規ブランチを作成し、リモートwork repoを切り替えられることを確認する。

対象リモート: Linux / Windows

前提:

- `manual/new-branch` が origin に存在しない
- リモートwork repoが clean である

手順:

```bash
uv run git-ssh-sync checkout <project> -b manual/new-branch --base main --dry-run
uv run git-ssh-sync checkout <project> -b manual/new-branch --base main
uv run git-ssh-sync status <project>
```

期待結果:

- [ ] `checkout -b --dry-run` が変更予定の操作を表示し、refやブランチを変更しない
- [ ] `checkout -b` が成功する
- [ ] origin に `manual/new-branch` が作成される
- [ ] リモートwork repoのカレントブランチが `manual/new-branch` になる

後片付け:

- 続くテストで利用しない場合、origin の `manual/new-branch` を削除する

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
origin のデフォルトブランチが main でない場合は --base の値を置き換える。
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

### 不正な checkout オプション

目的: `--base` を `-b` なしで指定した場合に CLI 入力エラーとして停止することを確認する。

対象リモート: 共通

前提:

- `<linux-project>` が登録済み

手順:

```bash
uv run git-ssh-sync checkout <linux-project> manual/existing --base main
```

期待結果:

- [ ] 終了コード 2 で停止する
- [ ] `--base can only be used with -b/--create-branch.` が表示される
- [ ] refやブランチを変更しない

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

## 既存リポジトリ取り込み

### attach dry-run と attach

目的: 既存の gateway/cache/work repo を `git-ssh-sync` 管理に取り込めることを確認する。

対象リモート: Linux / Windows

前提:

- 別のテスト用プロジェクト名を用意している
- origin、gateway、リモートcache、リモートwork repoが既に存在する
- リモートwork repoが clean である

手順:

```bash
uv run git-ssh-sync attach <project> --dry-run
uv run git-ssh-sync attach <project> --yes
uv run git-ssh-sync doctor <project>
```

期待結果:

- [ ] `attach --dry-run` が予定操作を表示し、repoを変更しない
- [ ] `attach --yes` が確認なしで必要な紐付けを行う
- [ ] `doctor` が成功する
- [ ] work repo の `gitsync` remote が設定された cache path と一致する

後片付け:

- 取り込みテスト専用の設定とrepoを削除する

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
このケースは clone 済みプロジェクトとは別名で実施する。
```

### attach の dirty 停止

目的: 既存work repoが dirty の場合、`attach` が停止することを確認する。

対象リモート: Linux / Windows

前提:

- attach 用の既存work repoがある
- work repoに未コミット変更を作れる

手順:

```bash
uv run git-ssh-sync attach <project> --dry-run
```

期待結果:

- [ ] dirty work tree を検出して停止する
- [ ] commit または stash を促すメッセージが表示される
- [ ] repo の紐付けを変更しない

後片付け:

- 未コミット変更を削除または commit する

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

## 診断と復旧

### doctor --repair

目的: `gitsync` remote や cache repo の不足を診断し、安全な修復だけを行うことを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している
- リモートwork repoが clean である
- テストとして `gitsync` remote URL を一時的に壊せる

手順:

Linux リモート:

```bash
ssh <linux-user>@<linux-host> '
  cd /home/<linux-user>/work/git-ssh-sync-manual &&
  git remote set-url gitsync /tmp/wrong-cache.git
'
uv run git-ssh-sync doctor <linux-project>
uv run git-ssh-sync doctor <linux-project> --repair
uv run git-ssh-sync doctor <linux-project> --repair --yes
uv run git-ssh-sync doctor <linux-project>
```

Windows リモート:

```bash
ssh <windows-user>@<windows-host> "powershell -NoProfile -Command \"Set-Location 'C:\Users\<windows-user>\work\git-ssh-sync-manual'; git remote set-url gitsync 'C:\wrong-cache.git'\""
uv run git-ssh-sync doctor <windows-project>
uv run git-ssh-sync doctor <windows-project> --repair
uv run git-ssh-sync doctor <windows-project> --repair --yes
uv run git-ssh-sync doctor <windows-project>
```

期待結果:

- [ ] 通常の `doctor` が不一致を検出する
- [ ] `doctor --repair` が修復予定を表示する
- [ ] `doctor --repair --yes` が確認なしで修復する
- [ ] 最後の `doctor` が成功する
- [ ] commit、stash、merge、rebase は行わない

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### recover

目的: 同期失敗後の入口として `recover` が診断と安全な修復を行うことを確認する。

対象リモート: Linux / Windows

前提:

- `clone` が完了している
- リモートwork repoが clean である
- cache repoまたは`gitsync` remoteを一時的に壊せる

手順:

```bash
uv run git-ssh-sync recover <project>
uv run git-ssh-sync recover <project> --yes
uv run git-ssh-sync doctor <project>
```

期待結果:

- [ ] `recover` が現状診断と次の操作を表示する
- [ ] `recover --yes` が安全な紐付け修復だけを行う
- [ ] `doctor` が成功する
- [ ] 既存作業の commit、stash、merge、rebase は行わない

後片付け:

- なし

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text
実行時は <project> を <linux-project> と <windows-project> に置き換えて両方確認する。
```

## ログ出力

### verbose / debug / log-file

目的: ログ詳細度とログファイル出力を確認する。

対象リモート: 共通

前提:

- `<linux-project>` が登録済み

手順:

```bash
uv run git-ssh-sync --verbose status <linux-project>
uv run git-ssh-sync --debug status <linux-project>
uv run git-ssh-sync --log-file /tmp/git-ssh-sync-manual.log status <linux-project>
test -f /tmp/git-ssh-sync-manual.log
```

期待結果:

- [ ] `--verbose` で INFO レベルのログが出る
- [ ] `--debug` で DEBUG レベルのログが出る
- [ ] `--log-file` で指定したファイルにログが出る
- [ ] コマンド本来の終了結果が変わらない

後片付け:

```bash
rm -f /tmp/git-ssh-sync-manual.log
```

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

## 後片付け

### git-ssh-sync 設定削除

目的: 手動テストで追加した設定を削除する。

対象リモート: 共通

手順:

```bash
uv run git-ssh-sync config remove <linux-project> --yes
uv run git-ssh-sync config remove <windows-project> --yes
```

期待結果:

- [ ] テスト用プロジェクト設定が削除される
- [ ] 既存の設定が残る

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### ローカル gateway repo 削除

目的: ローカルマシンに作成された gateway repo を削除する。

対象リモート: 共通

手順:

```bash
rm -rf ~/.git-ssh-sync/repos/<linux-project>
rm -rf ~/.git-ssh-sync/repos/<windows-project>
```

期待結果:

- [ ] テスト用 gateway repo が削除される

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### Linux リモートの repo 削除

目的: Linux リモートに作成された work repo と cache repo を削除する。

対象リモート: Linux

手順:

```bash
ssh <linux-user>@<linux-host> '
  rm -rf /home/<linux-user>/work/git-ssh-sync-manual
  rm -rf /home/<linux-user>/.git-ssh-sync/cache/<linux-project>.git
'
```

期待結果:

- [ ] Linux リモートのテスト用 work repo が削除される
- [ ] Linux リモートのテスト用 cache repo が削除される

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### Windows リモートの repo 削除

目的: Windows リモートに作成された work repo と cache repo を削除する。

対象リモート: Windows

手順:

```bash
ssh <windows-user>@<windows-host> "powershell -NoProfile -Command \"Remove-Item -Recurse -Force 'C:\Users\<windows-user>\work\git-ssh-sync-manual' -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force 'C:\Users\<windows-user>\.git-ssh-sync\cache\<windows-project>.git' -ErrorAction SilentlyContinue\""
```

期待結果:

- [ ] Windows リモートのテスト用 work repo が削除される
- [ ] Windows リモートのテスト用 cache repo が削除される

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### 設定ファイル復元

目的: テスト前の設定ファイルを復元する。

対象リモート: 共通

手順:

```bash
if [ -f ~/.config/git-ssh-sync/config.yaml.manual-test.bak ]; then
  mv ~/.config/git-ssh-sync/config.yaml.manual-test.bak ~/.config/git-ssh-sync/config.yaml
fi
```

期待結果:

- [ ] 退避していた設定ファイルが復元される
- [ ] バックアップがない場合、不要な変更をしない

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```

### origin テストブランチ削除

目的: テスト中に作成した origin ブランチを削除する。

対象リモート: 共通

手順:

```bash
git clone <origin-url> /tmp/git-ssh-sync-origin-cleanup
cd /tmp/git-ssh-sync-origin-cleanup
git push origin --delete manual/existing || true
git push origin --delete manual/new-branch || true
cd -
rm -rf /tmp/git-ssh-sync-origin-cleanup
```

期待結果:

- [ ] テスト用ブランチが存在する場合は削除される
- [ ] テスト用ブランチが存在しない場合でも後片付けを継続できる

結果:

- [ ] Pass
- [ ] Fail
- [ ] Skip

メモ:

```text

```
