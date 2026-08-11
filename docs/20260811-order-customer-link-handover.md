# 過去予約の実利用者アカウント紐付け 引き継ぎ報告

## 概要

代表者が連絡した予約を、本人確認後に実際の利用者の顧客アカウントへ手動で紐付けられるようにした。

- 元の連絡者、電話番号、SMS送信先、売上情報は変更しない。
- 名前一致による自動紐付けは行わない。
- managerだけが操作できる。
- 過去営業日の予約もmanagerが操作できる。
- 紐付けと解除の履歴を監査ログへ残す。

## 変更ファイル

- `core/models.py`
- `core/migrations/0052_order_service_recipient_customer.py`
- `core/serializers.py`
- `core/views.py`
- `core/admin.py`
- `core/test_order_customer_link.py`
- `frontend/src/api.js`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/20260811-order-customer-link-handover.md`

## 操作方法

1. managerで予約詳細を開く。
2. 「実利用者アカウントの紐付け」で名前または電話番号を検索する。
3. 本人確認済みの顧客を選び、「紐付けを保存」を押す。
4. 間違えた場合は「紐付けなし」を保存して解除する。

## API・権限

- `POST /api/orders/<id>/link-service-recipient/`
- body: `{ "customer_id": 123 }`
- 解除: `{ "customer_id": null }`
- manager以外は403。
- 他店舗顧客は400。
- 変更なしの場合は監査ログを重複作成しない。

## 顧客画面

紐付けられた顧客は、自分のマイページと予約詳細で対象予約を閲覧できる。連絡者側の既存閲覧権限は維持する。

## migration

- `0052_order_service_recipient_customer`
- `Order.service_recipient_customer`をnullableで追加する。
- `OrderServiceRecipientLinkLog`を追加する。
- 既存予約のデータ変換・削除はない。

## 検証結果

- 関連テスト: 6件成功
- 関連テスト（PostgreSQL 17一時DB）: 6件成功
- Django全テスト（SQLite）: 230件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI validation: 成功
- Python構文検査: 成功
- Vue production build: 成功
- `git diff --check`: 成功

初回CIで、nullableな実利用者顧客を`select_related`した状態の行ロックがPostgreSQLに拒否された。予約行だけをロックしてから顧客を読む最小修正を行い、一時PostgreSQL 17 DBの関連テストで回帰確認した。全テストはGitHub Actionsで再確認する。

## 本番反映後の手動確認

1. migration `0051`、`0052`が順番に適用されること。
2. テスト用の代表者予約をテスト用顧客へ紐付けること。
3. 元の連絡者が変わらないこと。
4. テスト用顧客のマイページへ履歴が表示されること。
5. 解除後は実利用者側から閲覧できないこと。

実顧客データで試験せず、専用テストデータを使うこと。
