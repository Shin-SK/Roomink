# 延長時間の予約反映 GPT引き継ぎ報告書

## 概要

予約作成時に既存の延長マスタをコースと一緒に選択できるようにし、延長の時間と料金を予約へ反映した。
予約詳細から延長を後付け・解除した場合も終了時刻を再計算する。

## 変更ファイル

- `core/serializers.py`
- `core/views.py`
- `core/test_order_extension_duration.py`
- `frontend/src/components/OrderForm.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/20260809-order-extension-duration-handover.md`

## 修正内容

- 有効な延長を新規予約画面に表示し、コースと同時に選択可能にした。
- 新規予約の終了時刻を `コース時間 + 延長時間` で自動計算する。
- 延長名・料金の既存スナップショットへ選択時の値を保存する。
- 延長料金を予約作成画面の合計金額へ加算する。
- 予約詳細から延長を追加・解除した場合も終了時刻と合計金額を再計算する。
- 延長後にシフトを超える、キャストの別予約と重なる、またはルームが重なる場合は適用を拒否し、予約を更新しない。
- 他店舗または無効な延長の指定を拒否する。
- 操作マニュアルの既存「延長を設定したい」を現行仕様へ更新した。

## DB・migration

- モデル変更なし。
- migration追加なし。

## テスト結果

- 延長関連テスト: 6件成功
- Django全テスト（SQLite）: 139件成功
- `python3 manage.py check`: 成功
- `python3 manage.py makemigrations --check --dry-run`: 変更なし
- OpenAPI検証: 成功
- Python構文検査: 成功
- Python依存整合性: 問題なし
- `npm audit --audit-level=high`: 脆弱性0件
- Vue production build: 成功
- PostgreSQL 17: GitHub Actionsで確認予定

## 残課題

- 延長マスタの「30分延長」「60分延長」等の実データ登録は店舗運用側で行う。
- 顧客向け公開Web予約に延長選択を出すかは、公開Web予約機能の仕様策定時に決める。

## 手動確認事項

- マネージャーで延長マスタへ名称・時間・料金を登録する。
- 新規予約画面で延長を選び、終了時刻と合計料金が想定どおりになることを確認する。
- 予約詳細で延長の追加・解除を行い、シフト超過・重複時の警告文を確認する。
