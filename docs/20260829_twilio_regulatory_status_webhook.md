# Twilio Regulatory Bundle ステータスWebhook 引き継ぎ

## 変更ファイル

- `core/views.py`
- `core/urls.py`
- `core/tests.py`

## 修正内容

- `POST /api/webhook/twilio/regulatory-status/` を追加した。
- 既存の `RequestValidator` と公開URL復元処理を再利用し、Twilio署名がないリクエストや不正署名を `403` で拒否する。
- `BundleSID`、`Status`、`FailureReason` を受け取る。
- 承認は `INFO`、差し戻しは `ERROR` として記録する。Sentryが本番で有効なら差し戻しの `ERROR` が監視対象になる。
- 差し戻し理由は改行を除去して最大500文字を運用ログへ記録する。
- WebhookではDBを更新しない。migrationも作成していない。

## テスト結果

- 関連テスト・OpenAPI: 11件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- Python構文検査: 成功

## 本番設定

デプロイ後、Twilio BundleのStatus callback URLを次へ変更する。

`https://roomink-0315e6e58623.herokuapp.com/api/webhook/twilio/regulatory-status/`

Herokuでは既存の以下設定を利用する。

- `TWILIO_AUTH_TOKEN`
- `TWILIO_WEBHOOK_PUBLIC_BASE_URL`
- `SENTRY_DSN`（差し戻しをSentry通知する場合）

## 手動確認事項

- デプロイ前にDjango全テストを実行する。
- デプロイ後に公開EndpointがGETでは受理されず、署名なしPOSTが403になることを確認する。
- Twilio ConsoleでStatus callback URLを更新後、次回の審査状態変更がHerokuログ／Sentryへ届くことを確認する。
- 実際の審査結果通知が来るまでは、正規署名付き本番Webhookの実受信は未確認となる。
