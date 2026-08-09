# 予約延長の入力ルール確定 — GPT向け引き継ぎ

## 変更ファイル

- `core/serializers.py`
- `core/views.py`
- `core/test_order_extension_duration.py`
- `frontend/src/components/OrderForm.vue`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/op/SettingsExtensions.vue`
- `frontend/src/pages/op/manualData.js`

## 修正内容

- 予約延長時間を5分単位に制限した。
- 最大延長時間を180分に制限した。
- 延長料金は従来どおり0円以上の自由入力とした。
- 直接入力、延長マスタ、既存予約への延長適用のすべてへ同じ制約を適用した。
- 延長操作をmanager / staffに限定し、castからのAPI操作を拒否した。
- `PENDING_FINALIZE`（会計待ち）までは延長可能とした。
- `DONE`（会計完了）と`CANCELLED`（キャンセル済み）は延長を拒否した。
- フロントエンドの入力欄へ5分刻み・180分上限を設定した。
- 運営画面内の操作マニュアルへ確定ルールを追記した。

## テスト

- 5分単位でない16分を拒否する。
- 180分を超える185分を拒否する。
- 不正入力時に予約終了時刻・延長・合計料金を更新しない。
- staffが会計待ち予約へ延長できる。
- castが延長APIを利用できない。
- 会計完了後は延長できない。
- 延長マスタにも同じ入力制約を適用する。
- 既存の延長正常系・競合検査・店舗分離を維持する。

## 検証結果

- 延長関連テスト: 17件成功。
- Django全テスト（SQLite）: 成功。
- `manage.py check`: 問題なし。
- `makemigrations --check --dry-run`: 変更なし。
- OpenAPI検証: 成功。
- Python構文検査・依存整合性検査: 成功。
- Vue production build: 成功。
- npm High/Critical監査: 0件。
- PostgreSQLテスト: GitHub Actionsで確認する。

## Migration

- なし。
- `Order.extension_duration`と`Order.extension_price`の既存スナップショットをそのまま利用する。

## 残課題

- 予約不可時間との重複検査は、予約不可時間モデルの実装時に追加する。
- 最大180分の店舗別設定化は行っていない。

## 手動確認事項

- 15分・30分・60分のクイック入力が動くこと。
- 16分や185分を入力した場合、分かりやすいエラーになること。
- 会計待ち予約では延長でき、会計完了後には適用できないこと。
