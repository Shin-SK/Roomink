# 予約延長の時間・料金直接入力 — GPT向け引き継ぎ

## 概要

予約の延長を固定マスタから選ぶだけでなく、予約ごとに延長時間（分）と料金（円）を直接入力できるようにした。既存の延長マスタは廃止せず、入力候補として利用できる。15分・30分・60分の簡単入力ボタンも追加した。

## 変更ファイル

- `core/models.py`
- `core/migrations/0045_order_extension_duration.py`
- `core/serializers.py`
- `core/views.py`
- `core/test_order_extension_duration.py`
- `frontend/src/api.js`
- `frontend/src/components/OrderForm.vue`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/cu/CuReservation.vue`
- `frontend/src/pages/op/manualData.js`

## 実装内容

- `Order.extension_duration` を追加し、予約時点の延長時間を保存する。
- migration `0045` で既存予約に紐づく延長マスタの時間を控えへ移す。
- 新規予約APIは `extension_duration` と `extension_price` を受け付ける。
- 延長マスタだけを渡す既存API利用は従来どおりマスタの時間・料金を使う。
- 延長マスタを候補として選んだ後、時間・料金を予約単位で上書きできる。
- マスタ時間と異なる場合、表示名は実時間に合わせて「15分延長」等になる。
- 既存予約の延長適用APIも、自由入力・候補選択・解除に対応する。
- 0分で料金だけを設定する入力は拒否し、DBを変更しない。
- 延長後のシフト超過、キャスト競合、ルーム競合の既存検証は維持する。
- 運営の予約作成・予約詳細に15/30/60分ボタンと直接入力欄を追加する。
- 顧客予約詳細に延長時間を表示する。
- 運営画面内の操作マニュアルを更新する。

## テスト結果

- 関連テスト: 11件成功
- Django全テスト（SQLite）: 成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI validation（警告を失敗扱い）: 成功
- Python構文検査: 成功
- Python依存整合性: 成功
- Vue production build: 成功
- `npm audit --audit-level=high`: 0件
- 一時SQLite DBを使ったローカルブラウザスモーク: 成功
  - 15分・3,000円の予約作成に成功
  - 予約詳細に延長時間・料金が表示
  - ブラウザコンソールエラー0件
- PostgreSQL: GitHub Actionsで実行予定

## migration

- 新規migration: `core.0045_order_extension_duration`
- スキーマ変更: `Order`へ非負整数の`extension_duration`を追加（既定値0）
- データ移行: 既存の`Order.extension`がある予約は、対応マスタの`duration`を保存する。
- 既存予約の終了時刻・料金・ステータスは変更しない。

## 残課題

- 延長時間・料金の店舗別上限や承認ルールは未確定のため追加していない。
- シフト外キャスト予約、予約不可時間、実利用者、70分前アラート、公開Web予約は別案件として扱う。
- 延長候補マスタの初期データは既存設定を利用し、本番データの追加・変更は行っていない。

## 手動確認事項

- 予約作成で15分・任意料金を入力し、終了時刻と合計料金が正しいこと。
- 延長マスタを選択すると時間・料金が入り、その後に上書きできること。
- 予約詳細から延長の追加・変更・解除ができること。
- 延長後にシフトや別予約と重なる場合、保存されないこと。
- 顧客予約詳細で延長時間と料金が分かりやすく表示されること。
