# 運営タイムライン 24時超え対応 引き継ぎ報告

## 変更ファイル

- `core/services/business_datetime.py`
- `core/serializers.py`
- `core/views.py`
- `core/test_schedule_business_datetime.py`
- `frontend/src/components/TimelineGrid.vue`
- `frontend/src/pages/op/Schedule.vue`
- `frontend/src/pages/op/RoomSchedule.vue`
- `docs/20260809-timeline-extended-time-handover.md`

## 修正内容

- 運営のキャスト別・部屋別タイムラインで、営業日を翌朝5時までとして予約を取得するようにした。
- 翌朝3時の予約を前営業日の`27:00`として返し、翌営業日へ重複表示しないようにした。
- シフト終了、予約開始・終了、インターバルを`24:00`から`29:00`の座標で表示するようにした。
- タイムラインの表示範囲を最大`29:00`まで拡張した。
- `27:00`等の空セルから予約作成を開いた場合、予約フォームへ実日付の翌日`03:00`として渡すようにした。
- 出勤セラピスト並び替え画面でもシフト終了を`29:00`表記にした。

## API互換性

- 既存の`start`と`end`は維持した。
- タイムライン予約データへ`start_time_extended`と`end_time_extended`を追加した。
- シフトデータへ`end_day_offset`と`end_time_extended`を追加した。
- 追加項目のみで、既存クライアントの必須入力は変更していない。

## migration

今回の変更ではモデルを変更しておらず、migrationは作成していない。

## テスト結果

- タイムライン専用テスト: 3件成功
- Django全テスト（SQLite）: 113件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI検証（fail-on-warn）: 成功
- Python構文検査: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- Vue production build: 成功

PostgreSQL 17での全テストは、PRのGitHub Actionsで実行する。

## 残課題

- 売上・精算・通知の営業日集計は後続の別PRで対応する。
- GitHub Actions公式ActionのNode 20廃止予定警告は別の保守PRで更新する。
- Twilio番号・SMS送信元の本番設定は事業者側手続き完了後に別途行う。

## 手動確認事項

- 18:00〜29:00のシフトがタイムライン上で翌朝5時まで表示されること。
- 翌朝3:00〜4:00の予約が前営業日の`27:00〜28:00`へ表示されること。
- 同じ予約が翌営業日のタイムラインへ重複表示されないこと。
- `27:00`の空セルを選ぶと、予約フォームが翌日03:00で開き、登録できること。
- キャスト別・部屋別の両表示で予約ブロックが同じ位置に出ること。
