# 店舗別カード決済URL 初期設定 引き継ぎ

## 変更ファイル

- `core/migrations/0061_seed_store_card_payment_urls.py`

## 変更内容

本番の既存店舗slugを照合し、カード決済URLの初期値を設定するデータmigrationを追加した。

- `tokyo-mens-esthe`: 東京メンズエステ用StarPay URL
- `rs-spa`: アールズスパ用StarPay URL

設定後もmanagerの「SMS文面設定」画面から店舗ごとに変更できる。逆migrationは、値がこのmigrationで設定したURLと一致する場合だけ空欄へ戻すため、その後の手動変更を上書きしない。

## 検証項目

- migrationのforward/reverse/forward
- `python3 manage.py check`
- `python3 manage.py makemigrations --check --dry-run`
- 関連カード決済SMSテスト
- Django全テスト（SQLite/PostgreSQL CI）
- Vue production build（CI）
- 本番release phase migration
- 本番管理画面の再読込と店舗別プレビュー

## 手動確認事項

- Twilio審査完了後に実SMSを安全な社内番号へ送信し、1通目の決済リンクと2通目のルーム案内を確認する。
- StarPay側でURLの契約先が各店舗と一致することを運営側でも確認する。
