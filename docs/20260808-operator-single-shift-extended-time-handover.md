# 運営側単日シフト 24時超え対応 引き継ぎ報告

作成日: 2026-08-08

## 結論

運営側の単日シフト登録・編集で、終了時刻を最大`29:00`まで入力し、保存後も同じ表記で再表示できるようにした。

週間シフト、キャスト申請、予約、タイムライン、売上、通知には変更を広げていない。本番デプロイ、push、既存DBへのmigration適用、外部サービスへの通信は行っていない。

## 変更ファイル

- `core/models.py`
- `core/serializers.py`
- `core/migrations/0042_shiftassignment_end_day_offset.py`
- `core/test_shift_assignment_extended_time.py`
- `frontend/src/pages/op/ShiftList.vue`
- `docs/20260808-operator-single-shift-extended-time-handover.md`

## 修正内容

### DB

`ShiftAssignment.end_day_offset`を追加した。

- `0`: 終了はシフト当日
- `1`: 終了はシフト翌日
- 既定値は`0`のため、既存シフトの意味は変わらない

例として、営業日`2026-07-31`の終了`29:00`は次の形で保存する。

- `end_time`: `05:00`
- `end_day_offset`: `1`

### API

既存の`start_time`と`end_time`は維持したまま、次を追加した。

- `end_day_offset`
- 読み取り用`end_time_extended`

`end_time_extended`は`05:00`とoffset 1を`29:00`へ戻す。従来の`23:00`とoffset 0は`23:00`のまま返す。

店舗timezoneと共通営業日時Serviceを使用し、次を検証する。

- 終了日時が開始日時より後である
- 最大`29:00`を超えない
- 同一キャストの既存シフトと重複しない
- 前日から翌日に跨ぐシフトと、隣接日のシフトも重複判定する
- 他店舗のキャスト・ルームを指定できない

### 運営画面

単日シフトの終了時間を`HH:MM`形式の入力欄へ変更した。`24:00`から`29:00`は保存時に通常時刻と翌日offsetへ変換する。

一覧と編集画面では、APIの`end_time_extended`を使用して`29:00`をそのまま表示する。

開始時間は今回の要件である`11:00〜29:00`に合わせ、従来どおり当日内の時刻入力を維持した。

## テスト結果

- 関連テスト: 7件成功
- Django全テスト（SQLite）: 93件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI validation（fail-on-warn）: 成功
- Python構文検査: 成功
- Vue production build: 成功
- `git diff --check`: 成功

Python 3.12.13、Django 5.2.16で実施した。

ローカルPostgreSQLは使用せず、既存ローカルDBにもmigrationを適用していない。push後はGitHub ActionsのPostgreSQL 17 jobで確認する。

## migration

- 新規migration: `0042_shiftassignment_end_day_offset`
- additiveな列追加のみ
- 既定値0のため既存行は当日終了として維持される

別のローカルTwilio準備branchにも未統合の`0042`が存在する。SMS・Twilio対応を後で統合する際は、mainのmigration履歴へrebaseし、Twilio側のmigration番号と依存を調整すること。

## 残課題

- 運営側週間シフトの24時超え対応
- キャスト側申請・承認の24時超え対応
- 予約・空き時間・タイムライン・売上等の営業日対応
- PostgreSQL 17でのCI確認
- 実ブラウザでの単日シフト追加・編集確認

## 次工程

次は別コミット・別PRで、運営側の週間シフト入力を最大`29:00`まで対応する。単日シフトと同じ共通Serviceと保存形式を使用し、ロジックを重複させない。

## ロールバック

本番反映前はbranchを破棄すれば戻せる。本番適用後にmigrationを逆適用する場合は、先に`end_day_offset=1`のデータが存在しないことを確認する。
