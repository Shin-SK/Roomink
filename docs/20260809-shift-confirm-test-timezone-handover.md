# 出勤確認通知テスト 日付境界修正 引き継ぎ報告

## 変更ファイル

- `core/tests.py`
- `docs/20260809-shift-confirm-test-timezone-handover.md`

## 修正内容

- 出勤確認通知テストで、予約日をOSローカル日付、時刻をUTCから作っていた不一致を修正した。
- `timezone.localtime(timezone.now())`を基準に、30分後の日付と時刻を同時に作るようにした。
- 業務コード、通知処理、外部送信処理は変更していない。

## テスト結果

- 対象テスト: 1件成功
- Django全テスト（SQLite）: 110件成功
- 実LINE・SMS・Twilio送信: なし

PostgreSQL 17での全テストはPRのGitHub Actionsで確認する。

## 残課題

- なし。
