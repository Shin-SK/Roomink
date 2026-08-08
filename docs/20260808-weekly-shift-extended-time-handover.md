# 週間シフト入力 24時超え対応 引き継ぎ報告

## 変更ファイル

- `core/views.py`
- `core/tests.py`
- `frontend/src/pages/op/ShiftWeekly.vue`
- `docs/20260808-weekly-shift-extended-time-handover.md`

## 修正内容

- 運営側の週間シフト入力で、終了時刻を `24:00` から `29:00` まで入力可能にした。
- フロントエンドで延長時刻を通常時刻と `end_day_offset` に変換し、既存の `ShiftAssignment` 保存形式へ渡すようにした。
- 登録済みシフトは `end_time_extended` を優先表示し、翌朝5時を `29:00` と表示するようにした。
- 週間APIで `end_day_offset` を受け取り、既存の営業日時Serviceを使ってリクエスト内の重複を判定するようにした。
- 月曜18:00〜29:00と火曜01:00〜04:00のような、日付をまたぐ重複も一括登録前に拒否する。
- 1件でも不正または重複がある場合に全件を登録しない既存仕様は維持した。

## テスト結果

- 週間シフト関連テスト: 17件成功
- Django全テスト（SQLite）: 96件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI検証（fail-on-warn）: 成功
- Python構文検査: 成功
- clean `npm ci`: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- Vue production build: 成功

PostgreSQL 17での全テストは、PRのGitHub Actionsで実行する。

## migration

今回の変更ではmigrationを作成していない。直前に導入済みの `ShiftAssignment.end_day_offset` を利用する。

## 残課題

- キャスト本人のシフト申請画面と、運営側の申請承認画面は別フェーズで24時超え対応する。
- Twilio番号・SMS送信元の本番設定は、事業者側手続き完了後に別途行う。

## 手動確認事項

- 週間シフト入力で終了を `29:00` として登録できること。
- 登録後、同じ週間画面に `29:00` と表示されること。
- `29:01` が画面上で拒否されること。
- 通常の `18:00〜23:00` 登録が従来どおり動作すること。
