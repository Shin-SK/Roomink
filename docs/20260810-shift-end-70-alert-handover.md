# シフト終了70分前アラート 実装引き継ぎ

## 概要

シフト終了70分前になった時点で、その後の時間帯に有効な予約がないキャストを運営ダッシュボードへ表示する機能を追加した。

- 判定区間: `シフト終了 - 70分` 以上、シフト終了未満
- 予約の重複判定: `予約終了 > アラート時刻` かつ `予約開始 < シフト終了`
- `CANCELLED` の予約だけを無効扱いとし、`REQUESTED` と確定・完了済み予約は有効扱い
- 欠勤シフトは対象外
- 24時を超えるシフト（例: 29:00）にも対応
- manager / staff のみ閲覧可能で、店舗をまたいだ情報は返さない
- LINEやSMSへの外部通知は行わず、今回の範囲はRoominkのダッシュボード表示のみ

## 変更ファイル

- `core/models.py`
  - シフト単位で1件だけ保持する `ShiftEndAlert` を追加
- `core/migrations/0049_shiftendalert.py`
  - `ShiftEndAlert` テーブルを作成
- `core/services/shift_end_alerts.py`
  - 70分前判定、OPEN / RESOLVED の同期、表示用集計を実装
- `core/views.py`
  - manager / staff向けAPIを追加
- `core/urls.py`
  - `GET /api/op/shift-end-alerts/` を追加
- `core/admin.py`
  - 調査用の読み取り専用表示を追加
- `core/test_shift_end_alert.py`
  - 時刻境界、予約状態、状態遷移、権限、店舗分離、29:00対応の回帰テストを追加
- `frontend/src/api.js`
  - アラート取得APIを追加
- `frontend/src/pages/op/Dashboard.vue`
  - 30秒間隔でアラートを取得し、対象キャスト・終了時刻・当日件数・完了売上を表示
- `frontend/src/pages/op/manualData.js`
  - 既存の操作マニュアルへ表示条件と画面内通知である旨を追記

## 状態管理

- 初回該当時に `OPEN` を作成する。
- アラート時間帯へ有効な予約が入った場合は同じ行を `RESOLVED` にする。
- その予約がキャンセルされ、まだシフト終了前なら同じ行を `OPEN` に戻す。
- シフトごとに一意制約があるため、再評価や複数回の画面取得で重複行は作成されない。

## 実行した検査

- 関連テスト: 8件成功
- Django全テスト（SQLite）: 203件成功
- Django全テスト（PostgreSQL 17の使い捨てDB）: 203件成功
- `python3 manage.py check`: 問題なし
- `python3 manage.py makemigrations --check --dry-run`: 差分なし
- migration 0049: 新規適用、0048への巻き戻し、0049の再適用がすべて成功（隔離SQLite DB）
- OpenAPI検証: 成功
- Python構文検査: 成功
- Python依存関係検査: High/Criticalを含む既知脆弱性なし
- `npm ci`: 成功
- `npm audit --audit-level=high`: 既知脆弱性0件
- Vue production build: 成功
- `git diff --check`: 問題なし

## 本番反映前後の確認事項

1. Heroku release phaseでmigration `0049`が成功すること。
2. managerとstaffのダッシュボードが通常どおり表示されること。
3. 検証用の当日シフトを使い、終了70分前の条件を満たした場合だけ警告が表示されること。
4. 対象時間帯へ予約を入れると警告が消えること。
5. その予約をキャンセルすると、シフト終了前なら警告が再表示されること。
6. cast / customerからAPIへアクセスしても403となること。

実データを使った条件再現は、誤予約や通知を避けるため今回のローカル検査では行っていない。

## 残課題

- LINE等への自動通知は未実装。画面内アラートの運用を確認してから別案件として追加する。
- 70分を店舗別・設定値にする要望が出た場合は、運用確定後に別migrationで対応する。
- 定期バッチではなくダッシュボード取得時に状態を同期する設計。画面を開かなくても外部通知する段階では、定期ジョブの追加が必要。
