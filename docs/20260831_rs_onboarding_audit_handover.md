# GPT引き継ぎ: R’s SPAアカウント発行と予約操作記録

## 変更目的

- 入力済みキャストを作り直さず、本人用ログインを発行できるようにする
- 予約について、作成者・最終操作担当・キャンセル担当を薄く追跡できるようにする
- 現在環境のデータを保持したまま、独自ドメイン本番と別ステージングへ移行する方針を固定する

## 変更ファイル

- `core/models.py`
- `core/services/cast_user.py`
- `core/serializers.py`
- `core/views.py`
- `core/migrations/0066_order_cancelled_by_order_created_by_order_updated_by.py`
- `core/test_cast_account_provisioning.py`
- `core/test_order_operator_tracking.py`
- `frontend/src/api.js`
- `frontend/src/pages/op/SettingsCasts.vue`
- `frontend/src/pages/op/OrderDetail.vue`
- `docs/20260831_rs_spa_account_onboarding.md`
- `docs/20260831_production_staging_domain_plan.md`

## 実装内容

### キャストログイン発行

- managerのみ `POST /api/casts/{id}/provision-account/` を利用可能
- 入力済みCastへUserとcast権限のUserProfileを紐付ける
- 発行済みの場合は、同じユーザー名のまま仮パスワードを再設定できる
- 他店舗Castは取得段階で404となる
- 共有用のログイン文面はフロントで一度だけ生成し、パスワードをAPI応答やDBの平文へ残さない

### 予約操作記録

- Orderへ `created_by`、`updated_by`、`cancelled_by` を追加
- 運営APIからの新規作成時に作成者と最終操作担当を保存
- PATCH、ステータス変更、延長・指名料・割引・媒体変更等で最終操作担当を更新
- キャンセル時にキャンセル担当を保存
- 予約詳細下部へ表示
- 公開Web予約など認証利用者がいない経路は作成者空欄を許容
- 過去データへ推測値のバックフィルは行わない

## 本番読み取り確認結果（2026-08-31）

- 東京メンズエステ: store 1
- アールズスパ: store 35
- アールズスパ専用managerあり
- アールズスパのCast 26名は店舗所属済み、本人用Userは未発行
- アールズスパの入力内容は別店舗へ混在していない

## 検証

- 関連15テスト成功
- Django全344テスト（SQLite）成功
- `manage.py check` 成功
- `makemigrations --check --dry-run` 差分なし
- Vue production build成功（586 modules transformed）

## 未実施・外部待ち

- 本番deployとmigration 0066適用
- R’s SPA実アカウントの発行（本人情報・共有タイミング確定後にmanagerが画面から実施）
- 独自ドメイン購入・接続
- 新規ステージング環境作成
- OpenAI API key / Slack webhook設定
