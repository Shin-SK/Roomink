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

## 新規契約店舗の追加手順

検索キーワード: `新規店舗追加`、`契約店舗追加`、`店舗開設`、`テナント追加`、`専用アカウント発行`

当面は店舗側が設定画面から自力で開設する方式にはせず、契約確定後にRoomink運営またはCodexが店舗作成、権限分離、初期検査を行ってから引き渡す。

### 依頼時に確認する情報

- 正式な店舗名
- 顧客向けURLに使う英字識別子（slug）。未指定なら候補を提案する
- 初回managerのユーザー名とメールアドレス
- 初期設定を空で始めるか、既存店舗を参考にするか
- 初期登録するルーム、キャスト、コース、オプション、延長、割引等
- 公開Web予約をすぐ有効にするか、入力・検査完了まで停止するか
- LINE、電話、SMSを使用するか。使用する場合は店舗専用設定の準備状況

パスワード、Auth Token、LINE Channel Secret等の秘密情報は、この文書やGitへ記録しない。

### Codexへ渡す依頼文の例

```text
新しい契約店舗「〇〇店」をRoominkへ追加してください。
既存店舗からデータと権限を完全に分離し、店舗専用URL、初回managerアカウント、必要な初期マスタを作成してください。
既存店舗を閲覧・更新できないことを権限別に検査し、本番反映後もスモークテストを実施してください。
```

### 実施内容

1. `CLAUDE.md`、Git状態、本番公開コミット、未適用migrationを確認する。
2. slugが既存の`Store.slug`と`StoreSlugAlias.slug`に重複しないことを確認する。
3. `Store`を正式名、slug、`Asia/Tokyo`で作成する。
4. ルーム、キャスト、顧客、シフト、コース、料金、予約、通知、精算等の初期データを、すべて新店舗の`store`へ紐付ける。
5. 既存店舗を参考にする場合も外部キーを共有せず、新店舗用レコードとして作成する。
6. 未確定のサンプル値には「仮」「要確認」と明示し、引き渡し時に一覧化する。
7. 初回managerを発行し、店舗専用URLとともに安全な経路で担当者へ渡す。
8. 自動テストと本番スモークで店舗分離を確認してから利用を開始する。

既存データを新店舗へ移管する場合、判別不能なデータを推測で移動しない。対象件数と所属を人間が確認し、本番データ変更前にバックアップと戻し方を決める。

### 初回managerの発行

```bash
python3 manage.py provision_store_manager \
  --store-slug <店舗slug> \
  --username <managerユーザー名> \
  --email <メールアドレス>
```

- コマンドが生成した仮パスワードは、指定担当者へ一度だけ共有する。
- 仮パスワードをグループチャット、docs、Git、テストコードへ保存しない。
- 初回ログイン後のパスワード変更を案内する。
- manager作成後、必要に応じてそのmanagerが店舗専用のstaff・castを登録する。

### 発行するURL

slugが`example-spa`の場合:

- 運営ログイン: `/login`
- 公開Web予約: `/s/example-spa/booking`
- 顧客ログイン: `/s/example-spa/login`
- 顧客マイページ: `/s/example-spa/mypage`

slugを変更した場合、旧slugは`StoreSlugAlias`として保持する。既配布URLを壊さないため、aliasを無断で削除しない。

### 必須の店舗分離検査

新店舗managerと既存店舗managerの両方で、最低でも次を確認する。

- ログイン後に自店舗名が表示される
- 自店舗のルーム、キャスト、顧客、予約、売上、設定だけが見える
- URLへ他店舗のIDを直接指定しても、閲覧・更新・削除できない
- staffがmanager専用設定へ入れず、castが運営用データへ入れない
- 同じ電話番号の顧客が別店舗に存在しても、店舗専用URLでは対象店舗の顧客情報だけが表示される
- 公開予約の選択肢、空き枠、予約確定先が指定店舗に限定される
- SMS、LINE、電話Webhook、通知ログが他店舗へ混ざらない
- CSV取込データがログイン中の店舗へだけ登録される

拒否レスポンスだけでなく、他店舗のDBレコードが更新されていないことも確認する。

### 検査と引き渡し

- 店舗分離・権限・公開URLの関連テスト
- Django全テスト（SQLite）
- 安全な一時DBが利用できる場合はPostgreSQLでも全テスト
- `python3 manage.py check`
- `python3 manage.py makemigrations --check --dry-run`
- Vue production build
- Heroku・Netlifyの公開コミットと本番反映確認
- 本番でmanagerログイン、店舗分離、公開URL、主要画面をスモーク確認

引き渡し時は、店舗名、slug、専用URL、managerユーザー名、入力済み項目、仮設定、テスト結果、店舗側の入力事項、外部サービスの審査待ち事項をまとめる。

公開Web予約、SMS、LINE、電話は、必要な入力・外部設定・安全な試験が完了するまで有効化しない。

店舗追加が頻繁になった段階で、運営専用の店舗開設画面または自動provisioningを別案件として検討する。現時点では、新規店舗追加のためだけに大規模なモデル変更やセルフサービス化は行わない。
