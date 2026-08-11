# キャスト複数日シフト申請 引き継ぎ報告

## 変更概要

キャストが同じ開始・終了時間、希望ルーム、メモを使い、複数日分のシフト希望を一度に提出できるようにした。従来の1日申請APIと画面操作は維持している。

複数日のうち1件でも入力不備、既存申請との時間重複、他店舗ルーム指定がある場合は、トランザクションを取り消して全件を未登録にする。1回の申請上限は31日。

## 変更ファイル

- `core/serializers.py`
  - 複数日入力用Serializerを追加
  - 日付重複、31日上限を検証
  - キャスト所属店舗以外の希望ルームを拒否
- `core/views.py`
  - `POST /api/cast/shift-requests/bulk-create/`を追加
  - 各日を既存の`CastShiftRequestSerializer`で検証・保存
  - 全件を`transaction.atomic()`で処理
- `core/test_shift_request_bulk_create.py`
  - 複数日申請と回帰・認可テストを追加
- `frontend/src/api.js`
  - 複数日申請API呼び出しを追加
- `frontend/src/pages/cast/CastShiftRequests.vue`
  - 日付の追加・削除UIを追加
  - 1日の場合は従来API、複数日の場合だけ新APIを利用
- `frontend/src/pages/op/manualData.js`
  - 既存シフト申請マニュアルへ複数日の操作を追記

## API仕様

`POST /api/cast/shift-requests/bulk-create/`

入力例:

```json
{
  "dates": ["2026-08-12", "2026-08-14", "2026-08-16"],
  "start_time": "18:00",
  "end_time": "05:00",
  "end_day_offset": 1,
  "desired_room": 1,
  "memo": "同じ内容でまとめて申請"
}
```

成功時は`201`と`created_count`、作成した申請の`created`配列を返す。キャストに紐づかないユーザーは`403`、入力不備や申請中シフトとの重複は`400`となる。

## テスト結果

- 関連テスト: 14件成功
- Django全テスト SQLite: 210件成功
- Django全テスト PostgreSQL 17（専用使い捨てDB）: 210件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI validation: 成功
- Python構文検査: 成功
- `git diff --check`: 成功
- `npm audit --audit-level=high`: 既知脆弱性0件
- Vue production build: 成功

## migration

既存の`ShiftRequest`を日付ごとに複数作成する方式のため、新規migrationはない。既存ローカルDB・本番DBへのmigration適用やデータ更新は行っていない。

## 残課題・手動確認事項

- キャスト画面で日付を2件以上追加し、共通の時間・希望ルームで送信できることを公開環境で確認する。
- 管理側のシフト申請一覧に、日付ごとの申請として表示されることを確認する。
- 「前週をコピー」「曜日パターン」は今回の初期仕様には含めていない。
