# カード決済二段階SMS・予約不可「入れ替え」対応 引き継ぎ

## 概要

- カード決済予約のSMSを次の2段階へ分離した。
  1. 予約確定時: 店舗別の共通決済URLを送る。
  2. 運営が入金を確認してボタンを押した後: ルーム名・住所・地図URL・注意事項を送る。
- 決済前SMSには顧客マイページURLとルーム情報を付けず、決済前に住所へ到達しないようにした。
- 予約不可時間の種別へ「入れ替え」を追加した。
- migration `0060_alter_castunavailabletime_type.py` を追加した。

## 変更ファイル

- `core/models.py`
- `core/serializers.py`
- `core/services/notify.py`
- `core/views.py`
- `core/migrations/0060_alter_castunavailabletime_type.py`
- `core/test_card_payment_sms_flow.py`
- `core/test_cast_unavailable_time.py`
- `core/tests.py`
- `frontend/src/api.js`
- `frontend/src/components/UnavailableTimeModal.vue`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/op/Settings.vue`
- `frontend/src/pages/op/SettingsSmsTemplates.vue`

## 実装内容

### 店舗別決済URL

`Store.card_payment_url` へ保存する。SMS設定画面からmanagerのみ編集でき、staffは閲覧のみ。

先方から受領した本番設定値:

- アールズスパ: `https://pay2.star-pay.jp/site/smt/shop.php?payc=A20254`
- 東京メンズエステ: `https://pay2.star-pay.jp/site/smt/shop.php?payc=A8496`

コードへ固定せず、デプロイ後に各店舗のSMS設定画面から上記URLを保存する。URL未設定時は1通目を送信せず、`CONFIG_MISSING / CARD_PAYMENT_URL_MISSING` を記録する。

既存のカード予約確認テンプレートは用途を自動変更しない。住所入り文面が決済前へ誤って流用されることを防ぐため、新しい2種類は安全な既定文から開始する。

### SMS送信フロー

- カード予約を確定すると `CARD_PAYMENT_REQUEST` を送信する。
- 注文詳細の「決済リンクSMSを送信・再送」から1通目を再送できる。
- 運営が「決済確認・住所SMSを送信」を押すと `CARD_PAYMENT_CONFIRMED` を送信する。
- 2通目はルーム未確定、未確定予約、取消済み、カード以外では送信できない。
- 2通目の成功送信は重複不可。`FAILED` / `CONFIG_MISSING` の場合は再試行できる。
- 確認日時と確認者を注文へ記録する。

### SMS設定画面

- カード決済URL
- カード決済前（決済リンク）
- カード決済完了後（ルーム案内）
- 通常の未設定・現金・PayPay文面

を店舗単位で設定・プレビューできる。差し込み項目へ `{payment_url}` を追加した。

## 検証結果

- 関連テスト: 15件成功
- Django全テスト: 293件成功
- `python3 manage.py check`: 問題なし
- `python3 manage.py makemigrations --check --dry-run`: 追加変更なし
- `git diff --check`: 問題なし
- Vue production build: 成功（480 modules）
- 実電話番号・実顧客・実SMS送信: 未使用

テストでは次を確認した。

- 1通目に決済URLが入り、住所・顧客マイページURLが入らない。
- 2通目に住所・地図URL・ルーム注意事項が入る。
- 2通目の二重送信を拒否する。
- URL未設定時にfail-closedとなる。
- カード以外・ルーム未定では2通目を拒否し、確認記録とSMSログを作らない。
- 店舗別設定が他店舗へ混ざらず、staffが変更できない。
- 予約不可時間の「入れ替え」が保存・表示できる。

## デプロイ後の作業

1. release phaseでmigration `0060` が成功したことを確認する。
2. 各店舗managerでSMS設定画面を開き、受領済み決済URLを保存する。
3. 本番の専用テスト顧客・架空電話番号でカード予約を1件作成する。
4. 予約確定後、1通目のSMSログ本文に決済URLだけが入り、住所がないことを確認する。
5. ルームを確定後、決済確認ボタンで2通目を送り、住所・地図・注意事項を確認する。
6. 同じボタンを再度押して二重送信が拒否されることを確認する。
7. テスト注文を安全に整理する。

## 未確認・残課題

- この報告時点では本番デプロイと本番URL保存は未実施。
- Twilio番号・審査が未完了のため、実回線への送達確認は未実施。
- Twilio利用可能後、実顧客ではなく管理するテスト番号で1通目・2通目を各1回だけ実送信確認する。
- ローカル既存SQLite DBはmigrationが古いため変更していない。検証は毎回作成・破棄される一時テストDBで実施した。
