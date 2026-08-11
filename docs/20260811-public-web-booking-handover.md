# 一般向けWeb予約 実装引き継ぎ

## 概要

公式サイト・広告等からログインなしで利用できるWeb予約を実装した。

- 公開URL: `/booking?store=<店舗ID>`
- 互換URL: `/public/booking?store=<店舗ID>` から上記へ転送
- SMSで電話番号を確認するまで、CustomerとOrderは作成しない
- SMS確認時に空き枠を再確認し、競合がなければ即時に `CONFIRMED` で確定
- 予約確定後は既存の顧客招待／予約確認SMSへ接続
- 本番では `PUBLIC_BOOKING_ENABLED=1` を明示するまで受付を開始しない
- 公開画面はRoominkロゴ／メインカラーへ統一し、スマートフォン利用を主対象とする
- 予約日を先に選び、その日の出勤キャストだけをルーム・エリア・シフト時間付きで表示する
- 100名規模でも名前検索、エリア絞り込み、段階表示で探せる
- コースは名前検索、施術時間絞り込み、段階表示で探せる

本番デプロイおよび実SMS送信は今回実施していない。

## 変更ファイル

- `config/settings.py`
- `core/admin.py`
- `core/models.py`
- `core/migrations/0050_publicbookingverification.py`
- `core/services/order_availability.py`
- `core/services/public_booking.py`
- `core/test_public_web_booking.py`
- `core/urls.py`
- `core/views.py`
- `frontend/src/api.js`
- `frontend/src/router.js`
- `frontend/src/pages/public/PublicBooking.vue`
- `frontend/src/pages/public/PublicBookingComplete.vue`
- `docs/20260811-public-web-booking-handover.md`

## 予約フロー

1. 匿名ユーザーが店舗と予約日を選択する。
2. 当日の出勤キャストを名前・エリア・ルームで検索し、担当を選ぶ。顧客自身が希望エリアを別入力する欄は設けない。
3. コースを名前・施術時間で絞り込み、開始時間・オプション・氏名・電話番号を選択／入力する。
4. コースの施術時間全体を確保できる枠だけを表示する。
5. SMS認証コードを要求する。
6. サーバーは予約内容を検証し、10分有効の認証情報だけを保存する。
7. この時点ではCustomerとOrderを作成しない。
8. 6桁コードの確認時に、店舗行とキャスト行をロックして空き枠を再検証する。
9. 電話番号が既存顧客と一致すればその顧客を使用し、未登録なら新規顧客を作成する。
10. Orderを `CONFIRMED` で即時確定する。
11. 既存の予約確認SMSと顧客アカウント招待を送る。
12. 完了画面へ予約番号、日時、担当、料金、ルーム、住所を表示する。

## セキュリティ・競合対策

- 認証コードは平文保存せず、Djangoのパスワードハッシャーでソルト付きハッシュ化する。
- SMSログにも認証コードを保存しない。
- 認証コードの有効期限は10分、入力上限は5回。
- 同一電話番号への発行は10分で3回まで。
- IP単位の発行は1時間10回、確認は1時間30回まで。
- 認証情報は1回だけ使用可能。
- SMS未設定・送信失敗時はCustomerとOrderを作らず、503でfail-closedとする。
- 認証後にもコース対象キャスト、店舗、オプション、シフト、予約不可時間、キャスト／ルーム競合を再検証する。
- 店舗単位のDBロックにより、別キャストが同じルームを同時確定する競合も直列化する。
- 既存顧客の氏名は公開入力で上書きしない。
- 他店舗のコース・オプションを混在させられない。
- BAN顧客は確定しない。

## API

- `GET /api/public/booking/options/?store=<id>&date=YYYY-MM-DD`
- `GET /api/public/booking/slots/?store=<id>&cast=<id>&course=<id>&date=YYYY-MM-DD`
- `POST /api/public/booking/request-verification/`
- `POST /api/public/booking/confirm/`

すべて匿名アクセス用だが、発行・確認APIにはDRFのスロットルを設定した。

## migration

- `0050_publicbookingverification`
- 公開予約のSMS確認情報を保持する `PublicBookingVerification` を追加
- Customer／Orderの既存構造は変更していない

## 必須環境変数

公開開始時に以下を確認する。

- `PUBLIC_BOOKING_ENABLED=1`
- `FRONTEND_URL=https://roomink.netlify.app`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_PHONE`（SMS送信可能番号）
- `SMS_DUMMY_MODE=0`

`PUBLIC_BOOKING_ENABLED` の既定値は `0`。番号・店舗情報・本番試験が揃うまで有効化しない。

## 実行結果

- 公開Web予約関連テスト: 10件成功
- Django全テスト SQLite: 220件成功
- Django全テスト PostgreSQL 17一時DB: 220件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- Python構文検査: 成功
- OpenAPI validation `--fail-on-warn`: 成功
- Python依存整合性: 問題なし
- Vue production build: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- `git diff --check`: 成功

## ブラウザ確認

実データを使わず、一時SQLite DBとSMSダミーモードで次を確認した。

- 店舗選択
- 顧客名・電話番号入力
- キャスト・コース選択
- コース時間に応じた空き枠表示
- オプション選択と合計金額
- SMS認証画面への遷移
- 6桁コード確認
- 即時予約確定
- 完了画面の予約番号・日時・料金・ルーム・住所
- 初回顧客の招待案内
- 390pxスマートフォン幅の表示
- Roominkロゴとメインカラーの統一
- 14日分の日付横スクロール
- ローカル専用の100名／5エリア仮データによる初期12名表示
- キャストの名前検索、エリア絞り込み、追加表示
- コースの名前検索、施術時間絞り込み、追加表示
- 選択キャストのルーム・エリア・シフト時間表示
- ブラウザコンソール警告・エラー0件

一時DB・架空電話番号のみを使用し、外部SMSは送信していない。

## 本番反映前の手動確認

1. TwilioのSMS送信可能番号が取得済みであること。
2. HerokuのTwilio環境変数を設定すること。
3. 本番ルーム住所・店舗名・キャスト・コース・オプションを確認すること。
4. 管理されたテスト電話番号でSMS認証と予約確認SMSを各1回確認すること。
5. 同じ枠を別ブラウザから選び、後勝ちが409で拒否されることを確認すること。
6. 予約が運営タイムラインへ `CONFIRMED` で表示されること。
7. 顧客招待URLから初回パスワードを設定し、予約詳細を閲覧できること。
8. 公式サイトへ載せる店舗別URLを確定すること。
9. 上記成功後にのみ `PUBLIC_BOOKING_ENABLED=1` を設定すること。

## 先方に修正してもらう仮情報

こちらで見本となる仮情報を先に登録し、先方には管理画面から正式内容へ修正してもらう。

- 店舗名
- ルーム名、エリアタグ、住所・アクセス案内
- 公開するキャスト、コース、オプション
- 公式サイト／広告へ掲載する店舗別予約URL
- キャンセル・変更時の案内文

Twilio審査とSMS番号取得だけは先方・契約管理者側の完了連絡が必要。

## 残課題

- Twilio実番号での本番SMS試験
- 公式サイト・広告からのリンク掲載
- 公開対象店舗の最終決定
- 利用規約・キャンセルポリシーの正式文言反映
- 期限切れPublicBookingVerificationの定期削除は、運用量を見て別タスクで追加する
