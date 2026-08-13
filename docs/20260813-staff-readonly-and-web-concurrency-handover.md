# Staff閲覧専用表示・本番同時処理改善 引き継ぎ報告

## 目的

本番スモークテストで確認した次の運用上の問題を修正した。

- staffが閲覧できる画面に、manager専用の追加・編集・削除操作が表示されていた
- staffのノート一覧APIは権限定義上は閲覧可能だったが、View内の重複チェックにより403になっていた
- HerokuのWeb処理が1ワーカーのみで、複数画面を同時に確認した際に一度H12タイムアウトが発生した

## 変更ファイル

- `core/views.py`
- `core/test_operator_api_permissions.py`
- `frontend/src/pages/op/CastNotes.vue`
- `frontend/src/pages/op/CastExpenses.vue`
- `frontend/src/pages/op/PointLogs.vue`
- `docs/20260813-staff-readonly-and-web-concurrency-handover.md`

## 修正内容

### Staff権限

- staffによる自店舗ノート一覧のGETを許可した
- ノートの作成・更新・削除・公開状態変更は従来どおりmanager限定とした
- staff表示時は以下の操作UIを非表示にした
  - ノート: 新規作成、編集、公開、アーカイブ、ピン留め、削除
  - 雑費: 追加、編集、削除
  - ポイント: 追加、編集、削除
- managerの既存操作は変更していない
- 店舗スコープは既存の`get_user_store()`による絞り込みを維持している

### Heroku同時処理

Heroku Config Varsへ次を設定し、dyno台数と料金プランを変えずに同時処理数を増やした。

- `WEB_CONCURRENCY=2`
- `GUNICORN_CMD_ARGS=--threads 2`

Heroku releaseはv88。Gunicornの2ワーカー起動をログで確認した。

## テスト結果

- 関連回帰テスト: 成功
- Django全テスト（SQLite）: 成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI validation: 成功
- Python構文検査: 成功
- `npm ci`: 成功
- `npm audit --audit-level=high`: High以上0件
- Vue production build: 成功
- `git diff --check`: 成功

PostgreSQL 17はPRのGitHub Actionsで実行する。

## 本番負荷確認

- 設定反映後health: 3回とも200、約0.86〜1.09秒
- 匿名`/api/auth/me/`への12件同時GET: 全件403（期待どおり）、約0.86〜1.61秒
- H10/H12、メモリ超過、worker異常終了、500: 設定反映後は検出なし

## migration

- migrationの作成なし
- Heroku Config Vars変更時のrelease phaseは既存migration確認のみ

## 残課題・手動確認

- 本番デプロイ後、staffでノート・雑費・ポイントを開き、一覧は読めるが変更ボタンが出ないことを確認する
- managerでは従来どおり変更ボタンが表示されることを確認する
- Herokuのメモリ超過やH12を継続監視する。問題がある場合は`WEB_CONCURRENCY`または`GUNICORN_CMD_ARGS`を見直す
- Twilioの審査状況・番号取得可否は別途Twilio Consoleで確認する

## ロールバック

- UI/API変更: 対象コミットをrevertして再デプロイする
- Heroku同時処理: `WEB_CONCURRENCY`と`GUNICORN_CMD_ARGS`をunsetし、従来の1ワーカー構成へ戻す

