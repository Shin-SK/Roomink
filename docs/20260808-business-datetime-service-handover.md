# 24時超え営業日時 共通Service 引き継ぎ報告

作成日: 2026-08-08

## 結論

24時を超える営業時間を後続のシフト・予約・タイムライン・売上で同じ基準により扱うため、DB非依存の共通Serviceと単体テストを追加した。

今回、モデル、migration、API、画面、既存データは変更していない。本番デプロイ、push、実DB更新も行っていない。

## 変更ファイル

- `core/services/business_datetime.py`
- `core/test_business_datetime.py`
- `docs/20260808-business-datetime-service-handover.md`

## 確定した初期仕様

- 拡張時刻の入力形式: `HH:MM`
- 既定の最大表示時刻: `29:00`
- `24:00`から`29:00`は翌日offset 1として扱う
- day offsetは0または1
- 開始時刻・終了時刻の双方で翌日offsetを扱える
- 既定の営業日境界: 05:00
- 区間は半開区間`[start, end)`
- 終了日時は開始日時より後でなければならない
- timezone-aware datetimeを使用する
- DSTで存在しない時刻、または二重に存在する曖昧なローカル時刻は拒否する
- 最大時刻、営業日境界、timezoneは引数で差し替え可能

## 公開関数

### `parse_extended_time(value, max_extended_hour=29)`

- `23:59 -> (time(23, 59), 0)`
- `24:00 -> (time(0, 0), 1)`
- `25:30 -> (time(1, 30), 1)`
- `29:00 -> (time(5, 0), 1)`
- 既定値では`29:01`以降を拒否する

### `format_extended_time(local_time, day_offset, max_extended_hour=29)`

- `time(5, 0), 1 -> 29:00`
- 秒・マイクロ秒を含む値は、表示時の情報欠落を避けるため拒否する

### `build_store_datetime(business_date, local_time, day_offset, timezone_name)`

営業日、通常時刻、offsetからtimezone-aware datetimeを作る。

例:

- 営業日: 2026-07-31
- 時刻: 05:00
- offset: 1
- timezone: Asia/Tokyo
- 結果: 2026-08-01 05:00 +09:00

### `build_business_interval(...)`

営業日基準の開始・終了datetimeを作り、終了が開始以前なら拒否する。

### `business_date_for_datetime(value, timezone_name, boundary_hour=5)`

指定timezoneへ変換後、05:00より前なら前日営業日へ帰属させる。05:00ちょうどから当日営業日になる。

### `business_day_range(business_date, timezone_name, boundary_hour=5)`

DB検索等で利用する営業日の半開区間を返す。

### `intervals_overlap(start_a, end_a, start_b, end_b)`

半開区間の重複を判定する。片方の終了と他方の開始が同時刻の場合は重複しない。

## テスト

### 専用テスト

- 20件成功
- 通常時刻
- 23:59
- 24:00
- 25:30
- 29:00
- 上限超過・不正形式
- 営業日境界04:59 / 05:00
- UTCから店舗timezoneへの変換
- 翌日offset
- 正の区間長
- 半開区間の重複
- America/New_YorkのDST不存在時刻
- America/New_YorkのDST曖昧時刻
- DST開始日の23時間営業日範囲

### 全体検査

- Django全テスト（SQLite）: 86件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- Python構文検査: 成功
- `git diff --check`: 成功

Python 3.12.12、Django 5.2.16で実施した。

ローカルPostgreSQLは起動していないため未実施。branchをpushしてPRを作成した後、既存GitHub ActionsのPostgreSQL 17 jobで確認する。

## 安全性

- DB importなし
- model変更なし
- migrationなし
- API変更なし
- UI変更なし
- 外部通信なし
- 既存データ更新なし
- 現時点では既存業務コードから未使用のため、現在の画面挙動は変わらない

## 次工程

次は別PRで「運営側単日シフト登録」の24時超え対応を行う。

想定内容:

- `ShiftAssignment`へ終了日のoffsetを追加
- additive migration、既定値0
- 既存のstart_time/end_timeを維持
- APIへoffsetまたは拡張表示時刻を追加
- 運営画面で`11:00〜29:00`を入力・再表示
- 保存・重複判定を今回のServiceへ統一
- 従来データはoffset 0のまま保持

週間シフト、キャスト申請、予約、タイムライン、売上、CSV、通知は次工程へ便乗させず、それぞれ別PRで進める。

## ロールバック

今回の変更は新規Service、専用test、報告書だけなので、この3ファイルを削除すれば戻せる。DBの逆操作は不要。
