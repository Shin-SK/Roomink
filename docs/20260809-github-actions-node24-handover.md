# GitHub Actions Node 24対応 GPT引き継ぎ報告書

## 概要

GitHub Actionsで表示されていたNode.js 20廃止警告を解消するため、公式ActionをNode.js 24対応メジャーへ更新した。

## 変更ファイル

- `.github/workflows/ci.yml`
- `docs/20260809-github-actions-node24-handover.md`

## 変更内容

- `actions/checkout@v4` → `actions/checkout@v5`
- `actions/setup-python@v5` → `actions/setup-python@v6`
- `actions/setup-node@v4` → `actions/setup-node@v5`

Python 3.12、Node.js 22、npm 11、PostgreSQL 17、テスト・監査・buildコマンドは変更していない。

## 検証

- 各公式リポジトリに対象メジャータグが存在することを確認した。
- YAML差分と空白エラーを確認した。
- 実際の動作はPRとmainのGitHub Actions全ジョブで確認する。

## migration・本番データ

- migrationなし。
- アプリコード、依存lockfile、本番データの変更なし。

## 残課題

- GitHubホステッドランナー側で新たな廃止予告が出た場合は、同様に公式Actionのメジャー更新を行う。
