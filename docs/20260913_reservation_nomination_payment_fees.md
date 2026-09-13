# 2026-09-13 予約入力の指名・決済表示対応

## 対応内容

- 予約の新規作成・編集画面に指名料選択を追加した。
  - 初期値は「指名なし」。
  - 店舗の有効な指名料マスターから選択する。
  - 選択した指名名・金額を予約へスナップショット保存し、合計へ反映する。
- カード決済時のオプション代について、予約単位で以下を切り替えられるようにした。
  - オプション代は現金（初期値）
  - オプション代もカードに含める
  - 選択値は `Order.card_include_options` に保存する。
  - 予約入力・予約詳細の双方で、カード請求額と来店時の現金受領額を分けて表示する。
- PayPay選択時、店舗のPayPay手数料率（既定5%）を使ったお客様請求額の目安を予約入力・予約詳細へ表示する。
- カード手数料も固定10%ではなく店舗設定値を使用するようにした。
- キャストマイページの給与見込み説明を、予約時間経過ではなく店舗側の「会計確定」後に反映されることが分かる文面へ変更した。

## API・権限

- 決済手数料設定APIのGETをmanager/staffに許可した。
- PATCHは従来どおりmanagerのみ。
- 他店舗または無効な指名料は予約へ設定できない。
- カード以外の支払方法では `card_include_options` を自動的にFalseへ戻す。

## 変更ファイル

- `core/models.py`
- `core/migrations/0067_order_card_include_options.py`
- `core/serializers.py`
- `core/views.py`
- `core/test_client_followup_updates.py`
- `frontend/src/components/OrderForm.vue`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/cast/CastMypage.vue`

## 実施済み確認

- `makemigrations --check --dry-run`: 追加差分なし
- `core.test_client_followup_updates`: 16件成功
- `core.tests.PaymentFeeSmokeTest` と `core.test_card_payment_sms_flow`: 7件成功
- `frontend npm run build`: 成功

## 未実施

- 本番デプロイ
- 本番ブラウザでの実データを使わない画面操作確認

本番反映時はマイグレーション適用後、予約の新規作成・再表示・編集について、指名なし/あり、カードのオプション現金/カード込み、PayPay 5%表示をそれぞれ確認すること。
