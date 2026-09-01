# Roomink 本番・ステージング・独自ドメイン移行計画

更新日: 2026-09-01

## 結論

現在の `roomink.netlify.app` と接続中のHeroku/PostgreSQLは、すでにR’s SPAの本番相当データが入っているため、そのまま本番として昇格させる。

現在環境をステージングへ改名して新しい本番DBへデータを移す方法は採用しない。データ再入力や移行漏れを避けるためである。

## 推奨構成

### 本番（現在環境を継続利用）

- 正式ドメイン: `roomink.net`（Cloudflare Registrarで取得済み）
- フロント: 現在のNetlify siteへ `app.roomink.net` を追加
- API: 現在のHeroku appへ `api.roomink.net` を追加
- DB: 現在のHeroku Postgresをそのまま利用
- `roomink.netlify.app`: 独自ドメイン公開後は本番への補助URLまたはリダイレクト元として扱う

### ステージング（後から新規作成）

- フロント: 新しいNetlify site
- API: 新しいHeroku app
- DB: 新しいPostgres DB
- URL: `staging.roomink.net` / `api-staging.roomink.net`
- 実顧客の電話番号、個人情報、本番SIP・SMS・LINE設定はコピーしない
- 必要なら匿名化した少量のサンプルデータだけ投入する

## 独自ドメイン取得後の作業

1. ~~ドメインの管理主体・支払者を確定する~~（Cloudflareで取得済み）
2. Netlifyへ本番フロント用サブドメインを接続する
3. Herokuへ本番API用サブドメインを接続する
4. DNSレコードを設定する
5. HerokuのCORS、CSRF、Cookie、公開URL設定へ新ドメインを追加する
6. Netlifyの本番API URLを新しいAPIドメインへ変更して再ビルドする
7. manager / staff / cast / customer のログインと主要操作を本番で確認する
8. Cookie、CSRF、画像、CSV、SMSプレビュー、CTIの回帰を確認する
9. 問題がなければ新ドメインを正式URLとして案内する

## データ保護

- ドメイン変更だけではDBの中身は変わらない
- 現在の本番相当データを新DBへ手作業で移さない
- 独自ドメイン設定前にHeroku Postgresバックアップを取得する
- 切替時は旧URLをすぐ削除せず、復旧経路として残す

## 2026-09-01 切替前保全

- 現在のHeroku/PostgreSQLを正本として維持する
- Herokuバックアップ `b005` を取得済み
- ローカル保全: `/Users/koyanagikokoro/Documents/Codex/Roomink-backups/roomink-before-domain-20260901.dump`
- SHA-256: `720e4492bbdc1e75f4a11dee25f8a293f1d9fc8c175cd8a492036b91c790ddac`
- `pg_restore --list` でバックアップ形式を検証済み
- Herokuへ `api.roomink.net` を追加済み
- Heroku Automatic Certificate Managementを有効化済み
- Cloudflare DNSとNetlifyカスタムドメインの接続後に正式切替する

独自ドメイン切替ではDBの作成・交換・初期化を行わない。R’s SPAが入力済みのデータをそのまま利用する。
