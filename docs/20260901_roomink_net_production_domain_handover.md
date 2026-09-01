# roomink.net 本番ドメイン切替 引継ぎ

更新日: 2026-09-01

## 最重要方針

現在のNetlify site `roomink`、Heroku app `roomink`、接続中Heroku Postgresを本番の正本として継続利用する。

R’s SPAが入力済みの店舗・ルーム・キャスト・顧客・予約等のデータを、新しいDBへ移したり初期化したりしない。独自ドメインは現在環境の入口へ追加するだけとする。

## 正式URL

- フロント: `https://app.roomink.net`
- API: `https://api.roomink.net`
- 旧フロント: `https://roomink.netlify.app`（当面残す）
- 旧API: `https://roomink-0315e6e58623.herokuapp.com`（当面残す）

## 切替前バックアップ

- Heroku backup: `b005`
- ローカル: `/Users/koyanagikokoro/Documents/Codex/Roomink-backups/roomink-before-domain-20260901.dump`
- SHA-256: `720e4492bbdc1e75f4a11dee25f8a293f1d9fc8c175cd8a492036b91c790ddac`
- 検証: `pg_restore --list` 成功（PostgreSQL custom archive、595 TOC entries）

## Heroku

- `api.roomink.net` を既存app `roomink`へ追加済み
- DNS target: `evening-aardwolf-d7hf0nvg4b4x98humbxcfrw8.herokudns.com`
- Automatic Certificate Managementを有効化済み
- Heroku ACM証明書発行済み（Let's Encrypt、`api.roomink.net`）
- `https://api.roomink.net/` と `/healthz` のHTTPS 200を確認済み
- release `v125` で次を正式URLへ切替済み
  - `FRONTEND_URL=https://app.roomink.net`
  - `TWILIO_WEBHOOK_PUBLIC_BASE_URL=https://api.roomink.net`

## Cloudflare DNS

設定済みレコード:

| Type | Name | Target | 初期Proxy |
|---|---|---|---|
| CNAME | `api` | `evening-aardwolf-d7hf0nvg4b4x98humbxcfrw8.herokudns.com` | DNS only |
| CNAME | `app` | `roomink.netlify.app` | Cloudflare proxy |
| TXT | `subdomain-owner-verification` | Netlify所有確認値 | DNS only |

`app.roomink.net` はCloudflare edge証明書でHTTPS配信でき、HTTP 200を確認済み。
Netlify側でもLet's Encrypt証明書が発行済みで、Primary domainのリンクがHTTPSになっている。

## Netlify

- 新しいsiteを作らず、現在のsite `roomink`へ `app.roomink.net` を追加する
- `roomink.netlify.app`は削除しない
- 現在の同一オリジン `/api/*` proxyを維持し、Cookie／CSRF方式を変えない
- `app.roomink.net` をPrimary domainに設定済み
- `roomink.netlify.app`はNetlify subdomainとして継続利用可能

## 本番環境変数

独自ドメインのHTTPS確認後に次を更新済み。

- `FRONTEND_URL=https://app.roomink.net`
- `DJANGO_ALLOWED_HOSTS`へ`api.roomink.net`を追加
- `DJANGO_CORS_ALLOWED_ORIGINS`へ`https://app.roomink.net`を追加し、旧URLも残す
- `DJANGO_CSRF_TRUSTED_ORIGINS`へ`https://app.roomink.net`を追加し、旧URLも残す
- `TWILIO_WEBHOOK_PUBLIC_BASE_URL=https://api.roomink.net`

## 2026-09-01 切替後確認

### 配信・セキュリティ

- `https://app.roomink.net/login`: HTTP 200
- `https://api.roomink.net/healthz`: HTTP 200
- 新フロント経由 `/api/health/`: HTTP 200
- 新フロント経由 `/api/auth/csrf/`: HTTP 200、Secure CSRF cookie発行
- 新フロントからのCSRF付きログインPOST: 認証エラー401まで到達し、CSRF 403にならないことを確認
- APIへ `Origin: https://app.roomink.net` を付けた場合、CORS許可ヘッダーを確認
- 本番JS／CSS assets: HTTP 200
- Herokuの切替直後ログに、ドメイン変更起因の500／Tracebackなし

### 画面

- managerログイン、castログイン、customerログイン: 表示成功
- R's SPA専用customerログイン: 表示成功
- R's SPA公開Web予約: 表示成功、設定どおり「Web予約は現在準備中です。」
- 上記をスマホ幅390pxでも確認し、ブラウザconsole errorなし
- 旧 `roomink.netlify.app` もHTTP 200で復旧経路として維持

### データ保持

本番DBを読み取り確認し、R's SPA（store 35）に次が保持されている。

- キャスト: 26名
- ルーム: 4件
- コース: 5件
- 顧客: 0件
- 予約: 0件

ドメイン切替ではDB作成、DB交換、データ初期化を行っていない。

## 切替後フルチェック

- manager / staff / cast / customerのログイン
- R’s SPA専用URLと店舗分離
- 予約作成・変更・キャンセルと操作担当記録
- 公開Web予約
- CSV顧客取込
- Cloudinary画像アップロード・表示・削除
- ノート作成・本文内画像・並べ替え
- SMSテンプレートとプレビュー
- カード決済前／決済確認後SMS
- CTI・SIP設定画面・着信履歴
- アプリ内AI案内とSlack通知
- ブラウザコンソールエラー

## ステージング

R's SPA単独運用中は、現在環境を開発兼本番として継続する。

東京メンズエステまたは次の契約店舗を運用開始する段階で、Netlify・Heroku・Postgresをすべて別で新設する。本番DBを共有せず、実顧客情報や本番SMS／SIP／LINE設定もコピーしない。

## 残作業

- クラコールから日本番号／接続情報を受領する
- 受領値を店舗電話・SIP・Voice／CTI設定へ登録する
- 実機着信、CTI表示、複数端末受話を確認する
- SMS用番号または送信設定を確定し、実送信を確認する
- R's SPA側の入力完了後に公開Web予約を有効化して実予約テストを行う
