# 過去予約の編集ロック 引き継ぎ報告

## 変更ファイル

- `core/services/order_policy.py`
- `core/permissions.py`
- `core/serializers.py`
- `core/views.py`
- `core/test_past_order_edit_lock.py`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/20260809-past-order-edit-lock-handover.md`

## 修正内容

- 店舗タイムゾーンの朝5時を境界として、現在の営業日より前の予約を過去予約と判定するようにした。
- 過去予約の修正、削除、確定、取消、会計進行、延長、指名料、割引、媒体変更をmanagerだけに許可した。
- スタッフとキャストによる拒否時は、予約データを一切更新しない。
- スタッフによる現在予約から過去日時への移動と、過去日時での新規作成も拒否するようにした。
- 現在営業日と未来の予約は、従来どおりスタッフが操作できる。
- 過去予約の閲覧は維持した。
- 予約APIへ読み取り専用の`is_past_business_day`と`can_modify`を追加した。
- 予約詳細画面では、操作できないスタッフへロック案内を表示し、変更操作を非表示または無効化した。
- managerが過去予約を変更した場合、予約ID・ユーザーID・操作名を通常ログへ記録するようにした。電話番号や顧客名は記録しない。
- リポジトリ内の操作マニュアルへ、過去予約の権限ルールを追記した。

## 権限仕様

- manager: 過去・現在・未来の予約を変更可能。
- staff: 過去予約は閲覧のみ。現在・未来の予約は従来どおり変更可能。
- cast: 過去予約の一般予約API変更は不可。
- 未認証: 既存どおり拒否。

## API互換性

- 既存URL、HTTPメソッド、入力項目は変更していない。
- 予約レスポンスに読み取り専用項目を2つ追加しただけで、既存項目は維持している。
- 権限拒否はHTTP 403とし、内部情報を返さない。

## migration

モデル変更はなく、migrationは作成していない。

## テスト結果

- 過去予約ロック専用テスト: 7件成功
- Django全テスト（SQLite）: 126件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI検証（fail-on-warn）: 成功
- Python構文検査: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- Vue production build: 成功

PostgreSQL 17での全テストは、PRのGitHub Actionsで実行する。

## 残課題

- 今回の操作記録はHeroku等の通常ログであり、DBに残る永続監査台帳ではない。
- 変更前後の値を保存する監査ログは、重要操作全体の監査設計として別PRで実装する。
- 過去予約の修正理由を必須入力にする場合は、運用ルール確定後に追加する。
- Twilio番号・SMS送信元の本番設定は、事業者側手続き完了後に別途行う。

## 手動確認事項

- スタッフで過去予約を開くとロック案内が表示され、支払方法・確定・会計・修正・取消を操作できないこと。
- スタッフが現在営業日・未来の予約を従来どおり操作できること。
- managerで過去予約を開くと修正できること。
- managerが過去予約を変更した際、通常ログへ予約ID・ユーザーID・操作名だけが記録されること。
- 過去予約を閲覧でき、リンク切れや403画面にならないこと。
