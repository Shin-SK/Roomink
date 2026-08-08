# キャスト当日画面の営業日対応 引き継ぎ報告

## 変更ファイル

- `core/views.py`
- `core/serializers.py`
- `core/test_cast_today_business_datetime.py`
- `frontend/src/api.js`
- `frontend/src/pages/cast/CastOrders.vue`
- `frontend/src/pages/cast/CastMypage.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/20260809-cast-today-business-date-handover.md`

## 修正内容

- キャストの当日予約APIを、店舗タイムゾーンの朝5時を境界とする営業日検索へ統一した。
- 深夜0時から朝5時までの予約を、前営業日の予約として一覧へ含めるようにした。
- キャスト画面からはブラウザのUTC日付を送らず、サーバーが店舗基準の現在営業日を決めるようにした。
- 既存クライアント向けの`date=YYYY-MM-DD`指定は引き続き利用できる。
- 深夜予約を`25:00`〜`29:00`形式で返し、予約一覧、マイページ、タイムライン、確認後の表示へ反映した。
- 出勤確認も同じ営業日判定へ統一し、深夜帯に当日のシフトを見失わないようにした。
- 24時を超えるシフト終了時刻を`29:00`形式で表示するようにした。
- 操作マニュアルへ深夜帯の表示ルールを追記した。

## API互換性

- `GET /api/cast/today/?date=YYYY-MM-DD`は維持している。
- `date`を省略した場合は店舗基準の現在営業日を返すように拡張した。
- 予約データへ`start_time_extended`と`end_time_extended`を追加した。
- シフトデータへ`end_time_extended`を追加した。
- 既存項目、URL、HTTPメソッドは変更していない。

## migration

モデル変更はなく、migrationは作成していない。

## テスト結果

- キャスト営業日専用テスト: 4件成功
- Django全テスト（SQLite）: 130件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI検証（fail-on-warn）: 成功
- Python構文検査: 成功
- Python依存整合性: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- Vue production build: 成功

PostgreSQL 17での全テストは、PRのGitHub Actionsで実行する。

## 残課題

- 深夜帯の表示は朝5時境界を前提としている。店舗別に境界時刻を変更する機能は今回の対象外。
- 実機のキャストアカウントで、深夜予約を含む表示確認はデプロイ後に行う。
- Twilio番号・SMS送信元の本番設定は、事業者側手続き完了後に別途行う。

## 手動確認事項

- 11:00〜29:00シフトで、27:00の予約が当日の予約一覧とマイページへ表示されること。
- 予約を「確認済み」にした後も、27:00〜28:00表示が維持されること。
- 深夜3時台にアクセスしても、前営業日のシフトと予約が表示されること。
- 朝5時以降の予約は次の営業日へ表示されること。
- 通常の日中予約と出勤確認が従来どおり使えること。
