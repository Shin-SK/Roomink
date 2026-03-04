# Step1 実装報告：運営ログイン + ルーターガード + ログアウト

## 概要

運営画面（/op/*）へのアクセスにログイン必須のガードを追加した。
バックエンドは既存APIをそのまま利用し、フロントエンド3ファイルのみの変更で完結。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `frontend/src/pages/op/Login.vue` | 新規 | ログインフォーム画面 |
| `frontend/src/router.js` | 変更 | ログインルート追加 + beforeEachガード + 認証キャッシュ |
| `frontend/src/components/LayoutOperator.vue` | 変更 | サイドバーにログアウトボタン追加 |

バックエンド変更：なし（既存の `/api/auth/login/`, `/api/auth/logout/`, `/api/auth/me/` をそのまま利用）

## 実装詳細

### 1. Login.vue（新規作成）

- 既存デザインシステム（CSS変数、cardコンポーネント、form-control等）を踏襲
- username / password フォーム
- `onMounted` で `api.me()` を1回呼び出し：
  - csrftoken cookieの発行を保証（初回アクセスでPOST時に403になる問題の対策）
  - 既にログイン済みなら `/op/dashboard` へリダイレクト
- ログイン成功時：`resetAuthCache()` でガードキャッシュをリセットし `/op/dashboard` へ遷移
- エラー時：サーバーからのメッセージ（「ユーザー名またはパスワードが正しくありません」等）をそのまま表示

### 2. router.js（変更）

- `/op/login` ルートを追加（`meta: { public: true }` でガード除外）
- `beforeEach` グローバルガード：
  - `/op/*` 以外のルート、および `meta.public` 付きルートはスルー
  - モジュールスコープ変数 `authed`（null/true/false）でキャッシュ
  - 初回のみ `api.me()` を呼び出し、以降はキャッシュを参照（毎遷移のAPIコール回避）
  - 未認証時は `/op/login` にリダイレクト
- `resetAuthCache()` をexport（Login.vue / LayoutOperator.vueから呼び出し）

### 3. LayoutOperator.vue（変更）

- `useRouter`, `api`, `resetAuthCache` をimport
- `onLogout()` 関数追加：`api.logout()` → `resetAuthCache()` → `/op/login` へ遷移
- サイドバー下部に「ログアウト」ボタンを配置（`btn-outline-primary btn-block`、Tablerアイコン `ti-logout`）

## 認証フロー

```
ブラウザ → /op/dashboard
  ↓ beforeEach ガード
  ↓ authed === null（初回）
  ↓ GET /api/auth/me/ (credentials: same-origin)
  ↓ 401 → authed = false → リダイレクト /op/login

/op/login
  ↓ onMounted: GET /api/auth/me/ → 401（csrftoken cookie発行）
  ↓ フォーム入力 → submit
  ↓ POST /api/auth/login/ (X-CSRFToken ヘッダー付き)
  ↓ 成功 → sessionid cookie セット
  ↓ resetAuthCache() → authed = null
  ↓ router.push('/op/dashboard')

/op/dashboard
  ↓ beforeEach ガード
  ↓ authed === null → GET /api/auth/me/ → 200
  ↓ authed = true → ページ表示

以降のページ遷移
  ↓ beforeEach ガード
  ↓ authed === true → キャッシュヒット → APIコールなし
```

## CSRF対策

- 既存 `api.js` の `getCookie('csrftoken')` + `X-CSRFToken` ヘッダーをそのまま利用
- Login.vue の `onMounted` で `api.me()` を呼ぶことで、Django CsrfViewMiddleware がレスポンスに `csrftoken` cookie をセットする
- これにより、フォーム送信時には確実にCSRFトークンが利用可能

## テスト手順（手動）

1. `http://localhost:5173/op/dashboard` にアクセス → `/op/login` にリダイレクトされること
2. 存在しないユーザーでログイン → エラーメッセージ表示
3. 正しいユーザーでログイン → `/op/dashboard` に遷移しKPIが表示されること
4. ブラウザリロード → ログイン状態が維持されていること
5. サイドバーの「ログアウト」ボタン押下 → `/op/login` に遷移
6. ログアウト後、`/op/schedule` に直接アクセス → `/op/login` にリダイレクト
7. `/cast/today` や `/cu/mypage` はガード対象外であること（正常にアクセスできる）

## 前提条件

- Django側に運営ユーザーが作成済みであること（`python manage.py createsuperuser` またはDjango admin経由）
- Docker環境でPostgreSQLが起動していること
- Vite dev serverが `localhost:5173` で起動し、`/api` が Django `localhost:8000` にプロキシされていること

## 次のステップ（Step2）

- 予約編集フォーム（OrderDetail.vueに日時・担当変更機能を追加）
- `PATCH /api/orders/:id/` の動作確認
- api.jsに `updateOrder()` メソッド追加（必要な場合）
