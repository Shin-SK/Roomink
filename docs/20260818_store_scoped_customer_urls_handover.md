# 店舗別顧客URL・店舗分離 引き継ぎ報告

## 目的

顧客向けWeb予約・ログイン・マイページを店舗別URLへ分離し、同じ電話番号の顧客が複数店舗に存在しても、指定店舗のアカウントだけで認証・表示されるようにした。

正式URLは `/s/<店舗URL識別子>/...` とする。`s` は Store の略。

## 主な変更ファイル

- `core/models.py`
  - `Store.slug` と、変更前URLを保持する `StoreSlugAlias` を追加。
- `core/migrations/0057_store_slug_and_alias.py`
  - 既存店舗へslugを付与。
  - `Roomink本店` は `東京メンズエステ` / `tokyo-mens-esthe`、アールズ系は `rs-spa` とする。
- `core/views.py`, `core/services/customer_context.py`, `core/services/public_booking.py`
  - 店舗slugによる公開予約・顧客認証・顧客APIの店舗分離。
- `core/services/customer_invitation.py`, `core/services/notify.py`
  - 招待・SMS内の顧客URLを店舗別URLへ変更。
- `core/management/commands/provision_store_manager.py`
  - 店舗slug指定で初回managerを発行する管理コマンド。
- `frontend/src/router.js`, `frontend/src/customerStore.js`
  - `/s/:storeSlug/` 配下のWeb予約・顧客画面ルートを追加。
- `frontend/src/pages/op/SettingsPublicBooking.vue`
  - managerが店舗URL識別子を変更できる欄と注意表示を追加。
- 顧客画面・公開予約画面一式
  - 店舗slugを維持して画面遷移・API呼び出しを行うよう変更。
- `requirements.txt`
  - 既知脆弱性4件を解消するため `sqlparse` を `0.5.5` から `0.6.0` へ更新。
- `core/test_store_scoped_customer_urls.py` ほか
  - 店舗分離・旧URL互換・権限制御・manager発行の回帰テスト。

## URLと権限

- アールズスパ公開予約: `/s/rs-spa/booking`
- 東京メンズエステ公開予約: `/s/tokyo-mens-esthe/booking`
- 顧客ログイン: `/s/<slug>/login`
- 顧客マイページ: `/s/<slug>/mypage`
- URL識別子の変更: managerのみ可能。staffは403。
- 変更前slugはaliasとして保存されるため、既配布URLからも同じ店舗へ到達できる。
- 旧 `/booking?store=<ID>` と `/cu/*` は互換性のため残している。

## migration

- 新規migration: `0057_store_slug_and_alias`
- 既存業務DBへのローカルmigration適用は行っていない。
- SQLite一時テストDBとPostgreSQL一時テストDBでmigrationを含むテストを確認した。
- 本番はHeroku release phaseの既存 `python3 manage.py migrate --noinput` で適用する。

## 検査結果

- Django全テスト（SQLite、3分割）: 277件成功
  - `core.tests`: 55件
  - `test_[a-m]*.py`: 67件
  - `test_[n-z]*.py`: 155件
- 関連テスト（SQLite）: 35件成功
- 関連テスト（PostgreSQL一時DB）: 44件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 差分なし
- OpenAPI validation: 成功
- Python構文検査: 成功
- `pip check`: 成功
- `pip-audit`: 既知脆弱性0件
- `npm audit --audit-level=high`: 0件
- Vue production build: 成功（480 modules）
- `git diff --check`: 成功

## 本番反映後の作業

1. Heroku releaseでmigration `0057` が成功したことを確認する。
2. `rs-spa` と `tokyo-mens-esthe` のmanagerアカウントを発行する。
3. 両managerでログインし、相手店舗の予約・顧客・売上・設定が見えないことを確認する。
4. 両店舗の公開予約URL、ログイン、旧URL互換を確認する。
5. 本番データの店舗所属は件数・名称を読み取り確認してから整理する。判別不能なデータは推測で移動しない。

## 残課題・手動確認

- Twilioの日本番号申請は審査待ち。承認後に電話・SMS番号とWebhook URLを設定し、実番号を使わない安全な確認から開始する。
- 先方入力済みデータのうち、どの店舗に属するか機械的に断定できないものは人間確認が必要。
- 店舗URL識別子は管理画面から変更可能だが、通常は変更しない運用とする。
- 正式独自ドメイン取得後、Netlify/Heroku/CORS/CSRF/FRONTEND_URLを正式URLへ切り替える。
