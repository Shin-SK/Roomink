# シフト申請・承認 24時超え対応 引き継ぎ報告

## 変更ファイル

- `config/settings.py`
- `core/models.py`
- `core/migrations/0043_shiftrequest_end_day_offsets.py`
- `core/serializers.py`
- `core/views.py`
- `core/test_shift_request_extended_time.py`
- `frontend/src/pages/cast/CastShiftRequests.vue`
- `frontend/src/pages/op/OpShiftRequests.vue`
- `docs/20260808-shift-request-extended-time-handover.md`

## 修正内容

- キャスト本人のシフト申請で、終了時刻を `24:00` から `29:00` まで入力可能にした。
- 運営側の申請承認でも同じ範囲を入力でき、承認後の実シフトへ翌日情報を引き継ぐようにした。
- 申請内容と承認内容の一覧表示を `29:00` 表記に対応した。
- 申請中シフトの重複判定を営業日時Serviceへ統一し、日付をまたぐ重複も拒否するようにした。
- CSVエクスポート、プレビュー、明示承認の往復でも `29:00` を維持するようにした。
- OpenAPIで共通の翌日フラグを同じenum名として出力するよう明示した。

## migration

- `0043_shiftrequest_end_day_offsets`
- `ShiftRequest.end_day_offset` と `ShiftRequest.approved_end_day_offset` を追加する。
- 既存行はデフォルト `0`（当日終了）となり、既存申請の時刻解釈は変わらない。
- データ移行や既存データ更新処理はない。

## テスト結果

- シフト申請・承認専用テスト: 7件成功
- Django全テスト（SQLite）: 103件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI検証（fail-on-warn）: 成功
- Python構文検査: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- Vue production build: 成功

PostgreSQL 17での全テストは、PRのGitHub Actionsで実行する。

## 残課題

- Twilio番号・SMS送信元の本番設定は、事業者側手続き完了後に別途行う。
- GitHub Actions公式ActionのNode 20廃止予定警告は、別の保守PRで更新する。

## 手動確認事項

- キャスト画面から `18:00〜29:00` の申請を送信できること。
- 運営画面で申請内容が `29:00` と表示され、そのまま承認できること。
- 承認後のシフト管理画面でも `29:00` と表示されること。
- `29:01` がキャスト申請・運営承認の双方で拒否されること。
- CSVへ `29:00` が出力され、戻し承認でも維持されること。
