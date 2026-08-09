# ルーム住所・顧客ページ表示 引き継ぎ報告

## 変更ファイル

- `core/models.py`
- `core/migrations/0044_room_address.py`
- `core/admin.py`
- `core/views.py`
- `core/test_room_address_customer_page.py`
- `frontend/src/pages/op/SettingsRooms.vue`
- `frontend/src/pages/cu/CuReservation.vue`
- `frontend/src/pages/cu/CuMypage.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/20260809-room-address-customer-page-handover.md`

## 修正内容

- Roomへ任意入力の住所を追加した。
- 運営のルーム管理画面から住所を登録・編集できるようにした。
- Django管理画面のルーム一覧へ住所を追加した。
- 顧客の予約詳細へ、ルーム住所とGoogle Maps検索リンクを表示するようにした。
- 顧客マイページの次回予約カードへ、ルーム名と住所を表示するようにした。
- 住所が未登録の場合は、顧客画面で準備中の案内を表示するようにした。
- リポジトリ内の操作マニュアルへ住所登録・確認手順を追記した。

## セキュリティ仕様

- 住所は予約確定後だけ顧客APIへ返す。
- `REQUESTED`と`CANCELLED`では住所を空文字として返す。
- 住所を閲覧できるのは、その予約に紐づく顧客本人だけ。
- 他顧客の予約詳細は既存どおりHTTP 404となる。
- 公開・未認証APIへ住所は追加していない。

## migration

- `core.0044_room_address`
- 空文字を初期値とする`Room.address`の追加だけで、既存行の削除・変換はない。
- Heroku release phaseの既存`python3 manage.py migrate`で自動適用される。
- 既存ルームの住所は空欄のまま維持されるため、デプロイ後に運営画面から入力する。

## テスト結果

- ルーム住所専用テスト: 3件成功
- Django全テスト（SQLite）: 133件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- `migrate --plan`: `core.0044_room_address`を確認
- OpenAPI検証（fail-on-warn）: 成功
- Python構文検査: 成功
- Python依存整合性: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- Vue production build: 成功

PostgreSQL 17での全テストは、PRのGitHub Actionsで実行する。

## 残課題

- 実際のルーム住所は未入力。運営側で確認した正式住所を登録する必要がある。
- 道順、入室方法、注意事項を個別管理する項目は今回追加していない。
- SMS本文へ住所を直接追加せず、既存方針どおり顧客ページへ誘導する。
- Twilio番号・SMS送信元の本番設定は、事業者側手続き完了後に別途行う。

## 手動確認事項

- マネージャーでルーム管理を開き、住所を保存・再編集できること。
- 確定済み予約の顧客マイページと予約詳細へ住所が表示されること。
- 地図リンクが登録住所のGoogle Maps検索を開くこと。
- 申請中・キャンセル済み予約では住所が表示されないこと。
- 住所未登録のルームでは、準備中の案内が表示されること。
- 運営側が正式住所を確認してから本番データへ入力すること。
