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
- DNS反映後に証明書状態とHTTPS 200を確認する

## Cloudflare DNS

追加するレコード:

| Type | Name | Target | 初期Proxy |
|---|---|---|---|
| CNAME | `api` | `evening-aardwolf-d7hf0nvg4b4x98humbxcfrw8.herokudns.com` | DNS only |
| CNAME | `app` | Netlifyが指定するtarget（通常は`roomink.netlify.app`） | DNS only |

## Netlify

- 新しいsiteを作らず、現在のsite `roomink`へ `app.roomink.net` を追加する
- `roomink.netlify.app`は削除しない
- 現在の同一オリジン `/api/*` proxyを維持し、Cookie／CSRF方式を変えない

## 本番環境変数

独自ドメインのHTTPS確認後に次を更新する。

- `FRONTEND_URL=https://app.roomink.net`
- `DJANGO_ALLOWED_HOSTS`へ`api.roomink.net`を追加
- `DJANGO_CORS_ALLOWED_ORIGINS`へ`https://app.roomink.net`を追加し、旧URLも残す
- `DJANGO_CSRF_TRUSTED_ORIGINS`へ`https://app.roomink.net`を追加し、旧URLも残す
- `TWILIO_WEBHOOK_PUBLIC_BASE_URL`は新APIの動作確認後に変更する。先に変更しない

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

正式本番が安定してから、Netlify・Heroku・Postgresをすべて別で新設する。本番DBを共有せず、実顧客情報や本番SMS／SIP／LINE設定もコピーしない。
