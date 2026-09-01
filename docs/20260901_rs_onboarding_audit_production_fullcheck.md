# R's SPA アカウント発行・予約操作履歴 本番反映／フルチェック引き継ぎ

## 対象

- PR: #60 `R's SPA account onboarding and thin order audit`
- main merge commit: `6da2b5c786142cf94d5aa5198b8424b2ff78283a`
- Heroku release: `v120`
- 実施日: 2026-09-01

## 本番反映した内容

### キャスト本人用ログイン

- manager が既存キャストへログイン用ユーザー名・仮パスワードを発行できる。
- キャスト本体や入力済みプロフィールを作り直さず、既存 `Cast` に `User` を紐付ける。
- 発行済みアカウントではユーザー名を固定し、仮パスワードの再設定だけを許可する。
- staff、cast、他店舗managerからの発行を拒否する。
- 平文パスワードをDB・ログ・継続的なAPI応答へ保存しない。

### 予約の簡易操作履歴

- `Order.created_by`: 予約作成者
- `Order.updated_by`: 最終更新者
- `Order.cancelled_by`: キャンセル実行者
- 予約詳細下部へ、値がある項目だけ表示する。
- 既存予約は履歴不明のため `null` のままとし、推測による埋め戻しはしない。

## 自動チェック結果

- Django 5.2.17
- Django system check: 成功
- migration差分検査: 差分なし
- migration `0066`: 本番適用済み
- SQLiteフルテスト: 344件成功
- GitHub Actions / SQLite: 成功
- GitHub Actions / PostgreSQL 17: 成功
- GitHub Actions / Backend checks: 成功
- GitHub Actions / Frontend checks: 成功
- `pip-audit`: 既知脆弱性0件
- `npm audit --audit-level=high`: 0件
- Vue production build: 成功
- `git diff --check`: 成功

## 本番環境チェック結果

### 配信・稼働

- Heroku web dyno: up
- Heroku health: HTTP 200
- Netlifyトップ: HTTP 200
- Netlify配信中JS/CSSとローカルproduction buildのasset名が一致
- migration `0066_order_cancelled_by_order_created_by_order_updated_by`: 適用済み
- デプロイ後ログ: 予期しない500／Tracebackなし

### 実ブラウザ

- R's SPAのmanagerセッションでダッシュボード表示成功
- R's SPAキャスト設定に26名が表示される
- キャスト編集モーダルに「本人用ログイン」欄が表示される
- 未発行キャストではユーザー名、8文字以上の仮パスワード、無効状態の発行ボタンを確認
- R's SPAアカウントから他店舗の予約IDへ直接アクセスした場合、対象なしとなることを確認
- `/login`、`/cast/login`、`/cu/login`、`/s/rs-spa/login`、`/op/dashboard`: HTTP 200
- R's SPA顧客ログイン画面: 表示成功、console errorなし
- R's SPA公開予約画面: 「Web予約は現在準備中です」を表示、console errorなし

## 意図した未確認／停止項目

### R's SPA公開Web予約

店舗設定で公開予約が停止中のため、公開予約options APIはHTTP 503と
`Web予約は現在準備中です。`を返す。障害ではない。
本番試運転を開始する直前に、キャスト・コース・シフト入力を確認してから公開する。

### 全権限での本番保存操作

本番に専用QAアカウントを新規作成すると、永続的なアクセス権とテスト顧客・キャストを
追加することになるため、今回は安全上実施していない。
manager／staff／cast／customer、店舗外アクセス、発行・再設定、予約作成・更新・キャンセルは
SQLite 344件とGitHub ActionsのSQLite／PostgreSQLで検証済み。

R's SPAから最初の実予約が入った後に、詳細画面で作成者・更新者・キャンセル実行者の
実データ表示を追加確認する。

### 外部サービス

- OpenAI APIキーとSlack webhookは本番設定済み。
- Slack疎通はHTTP 200 `ok`を確認済み。
- AI自動返信は安全のためOFFのまま。
- 日本の電話番号取得は外部手続き待ち。仮の海外番号によるVoice／CTI疎通は確認済み。

## 次に進める順番

1. 橋本さん個人のR's SPA managerアカウントを確定し、共有アカウント運用を終了する。
2. R's SPAのstaff人数・氏名を確認し、個別staffアカウントを発行する。
3. 26名のキャストへ本人用ログインを順次発行する。manager画面の今回追加欄を使う。
4. 先方のキャスト・SMS・シフト入力完了後、こちらで実予約を数件作成して総合動作確認する。
5. 公開Web予約を有効化し、予約確定、SMS、顧客マイページ、店舗分離を実データで確認する。
6. 日本番号はクラコールの回答とTwilio問い合わせを並行して進め、取得後に本番番号へ差し替える。
7. `roomink.com`等の正式ドメインを取得し、現在のHeroku／Netlify／本番DBへ割り当てる。
8. 現在の本番DBを共有しない独立したstaging環境を、その後に新設する。
9. サポートAIはFAQ回答とSlack通知から限定運用を開始し、自動送信は評価後に有効化する。

## 環境分離の注意

現在のNetlify／Heroku／PostgreSQLには先方が入力した本番データがあるため、
この組をそのまま本番として正式ドメインへ昇格させる。
`roomink.netlify.app`をデータ共通のままstaging扱いにはしない。
stagingは別Heroku app、別DB、別Netlify site、別外部サービス設定で作成する。
