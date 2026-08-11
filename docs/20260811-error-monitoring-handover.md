# エラー監視基盤 引き継ぎ報告

## 概要

DjangoとVueへSentryのエラー監視基盤を追加した。監視先情報が未設定の環境では初期化せず、外部通信も行わない。

## 変更ファイル

- `config/monitoring.py`
- `config/settings.py`
- `core/test_monitoring.py`
- `requirements.txt`
- `frontend/src/monitoring.js`
- `frontend/src/main.js`
- `frontend/package.json`
- `frontend/package-lock.json`
- `docs/20260811-error-monitoring-handover.md`

## 安全設定

- `SENTRY_DSN` / `VITE_SENTRY_DSN` が空なら監視を無効化する。
- Cookie、Authorization、CSRFヘッダー、リクエスト本文を送信前に削除する。
- 個人情報の標準送信を無効化する。
- 性能追跡とセッションリプレイは使用しない。
- DSN未設定のローカル開発・CI・本番環境の既存動作を変更しない。

## 必要な環境変数

Heroku:

- `SENTRY_DSN`
- `SENTRY_ENVIRONMENT=production`（任意）
- `SENTRY_RELEASE`（任意。未設定時はHerokuのcommit値を利用）

Netlify:

- `VITE_SENTRY_DSN`
- `VITE_SENTRY_ENVIRONMENT=production`（任意）
- `VITE_SENTRY_RELEASE`（任意）

## 検証結果

- 監視設定テスト: 3件成功
- Django全テスト（SQLite）: 223件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- Vue production build: 成功
- npm High/Critical脆弱性: 0件

PostgreSQL 17の全テストはGitHub Actionsで確認する。

## 残作業

- Sentry側でDjango用・Vue用のプロジェクトを作成する。
- HerokuとNetlifyへ各DSNを登録する。
- 個人情報を含まない意図的なテスト例外を各1回送信し、受信と通知を確認する。
- テスト後にSentryの通知先と担当者を確定する。
