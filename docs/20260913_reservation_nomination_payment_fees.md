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
- Django全テスト: 351件成功
- `frontend npm run build`: 成功
- `npm audit --audit-level=high`: 高重大度以上0件
- GitHub PR #68 の全チェック成功後にmainへマージ
- Heroku release v131として本番反映し、`core.0067_order_card_include_options` のマイグレーション成功
- `https://api.roomink.net/healthz`: 200 / `ok: true`
- `https://app.roomink.net/login`: 200。本番配信中の遅延読込JSに以下の表示文言が含まれることを確認
  - 指名料
  - オプション代は現金
  - オプション代もカードに含める
  - PayPay請求額（目安）
  - 予約時間を過ぎただけでは反映されません

## 本番フルチェック

- アールズスパ内に確認専用のmanager/staff/cast、顧客、コース、オプション、指名料、ルーム、シフトを一時作成し、通常データから分離して実施した。
- 本番APIで予約を新規作成し、保存直後の再取得で以下を確認した。
  - 指名料3,000円
  - オプション4,000円
  - コース17,000円
  - 合計24,000円
  - カード決済でオプションを含める設定が保持される
- 同じ予約を編集・再取得し、カードのオプション支払設定が保持されることを確認した。
  - オプション込み: カード対象24,000円、手数料10%込み26,400円
  - オプション現金: カード対象20,000円、手数料10%込み22,000円、現金受領4,000円
- PayPayへ変更・再取得し、カード固有設定がFalseへ戻り、手数料5%込み25,200円になることを確認した。
- ステータスを `REQUESTED → CONFIRMED → PENDING_FINALIZE → DONE` と遷移させた。
- キャスト側当日売上APIで、会計確定前は0円、確定後は売上24,000円・給与見込み10,500円へ反映されることを確認した。
- staffで手数料設定を取得できること、staffによる変更は403で拒否されることを確認した。店舗のPayPay 5%・カード10%設定は変更されていない。
- 上記リクエストは、意図した権限拒否1件を除いてすべて200/201。確認区間の本番ログに500エラーおよびTracebackなし。
- 確認用に作成した予約・マスター・アカウント・シフトは、IDと名称を照合したうえですべて削除し、各件数が0になったことを確認した。

## 補足

- ブラウザ自動操作は接続が不安定だったため、画面内の最終送信操作ではなく、本番配信アセットの表示文言確認と、本番APIによる作成・保存・再表示・編集・会計確定を組み合わせて確認した。
- 実機では、予約入力画面のカード/PayPay切替時の見た目と、キャストマイページの説明文を最終確認対象とする。
