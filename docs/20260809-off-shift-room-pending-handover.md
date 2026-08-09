# GPT引き継ぎ報告書：シフト外キャスト・ルーム未定予約

## 概要

manager / staffが、指定日にシフトのないキャストへ予約を作成できるようにした。シフト外予約はルーム未定で保存し、後から予約時間を含むシフトを登録した時点で、そのシフトのルームを安全に自動割当する。

## 変更ファイル

- `core/models.py`
- `core/serializers.py`
- `core/views.py`
- `core/services/notify.py`
- `core/migrations/0047_alter_order_room.py`
- `core/test_off_shift_room_pending.py`
- `frontend/src/components/OrderForm.vue`
- `frontend/src/components/TimelineGrid.vue`
- `frontend/src/pages/op/Dashboard.vue`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/op/ShiftList.vue`
- `frontend/src/pages/op/manualData.js`
- `frontend/src/assets/css/components/_schedule.scss`

## 実装内容

- `Order.room`をnullableに変更した。
- シフト内予約は従来どおりシフトのルームを自動設定する。
- シフト外予約はmanager / staffだけが作成・変更でき、`room=None`で保存する。
- castおよびcustomerはシフト外予約を作成できない。
- シフト外でもキャスト予約重複・インターバル・予約不可時間を検査する。
- ルーム未定予約を含むシフトを新規登録すると、ルーム重複を再検査してから予約へルームを自動割当する。
- 予約の一部しか含まないシフト、または使用中ルームへの割当は拒否する。
- 有効予約を含むシフトの単純削除を拒否する。
- タイムラインは出勤キャストを先、非出勤キャストを後に表示し、非出勤者をグレー表示する。
- 予約タイムライン、予約詳細、当日ダッシュボードに「シフト外」「ルーム未定」を表示する。
- キャスト当日画面、顧客予約詳細、予約確認通知はルーム未定でも500にならない。
- 既存の操作マニュアルを新仕様へ更新した。

## Migration

- `0047_alter_order_room.py`
- `core_order.room_id`へNULLを許可するスキーマ変更のみ。
- 既存データの更新・削除・変換は行わない。

## テスト結果

- 新規回帰テスト：10件成功
- 関連テスト：59件成功
- Django全テスト（SQLite）：170件成功
- `manage.py check`：成功
- `makemigrations --check --dry-run`：追加差分なし
- OpenAPI validation（fail-on-warn）：成功
- Python構文検査：成功
- Python依存整合性：成功
- Vue production build：成功
- `npm audit --audit-level=high`：脆弱性0件
- `git diff --check`：成功

GitHub ActionsでSQLite / PostgreSQL 17を再実行し、両方greenであることをマージ条件とする。

## 本番反映後の確認

1. managerで予約タイムラインを開き、非出勤キャストが下部へグレー表示されること。
2. 非出勤キャストを選択すると警告が表示されること。
3. テスト用予約を作る場合は、ルーム未定で作成されること。
4. 予約時間を含むシフトを登録すると、ルームが予約へ割り当たること。
5. 当日ダッシュボードからルーム未定警告が消えること。
6. Heroku release phaseでmigration 0047が成功すること。

実データを使った本番作成・変更は自動スモークでは行わない。

## 残課題

- シフト外予約作成時のキャストLINE通知は別案件。
- シフトの編集で既存予約を別ルームへ一括移動する機能は今回対象外。
- 当欠時の予約再割当・キャンセル支援は別案件。
- 一般公開Web予約では引き続きシフト外予約を許可しない。
