# Step7 実装報告：AWS App Runner 本番起動準備

## 概要

ローカル開発用の `runserver` から、本番運用可能な `gunicorn + whitenoise` 構成に切り替え。
環境変数ベースで CORS / CSRF / ALLOWED_HOSTS を制御し、App Runner の疎通確認用 `/healthz` を追加。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `requirements.txt` | 変更 | gunicorn, whitenoise 追加 |
| `Dockerfile` | 変更 | CMD を entrypoint.sh に変更 |
| `entrypoint.sh` | 新規 | collectstatic → gunicorn 起動 |
| `config/settings.py` | 変更 | WhiteNoise, CSRF_TRUSTED_ORIGINS, CORS env対応, STATIC_ROOT |
| `config/urls.py` | 変更 | `/healthz` エンドポイント追加 |

## 実装詳細

### 1. requirements.txt

```
gunicorn==23.0.0
whitenoise==6.9.0
```

### 2. Dockerfile + entrypoint.sh

- `CMD` を `entrypoint.sh` に変更
- entrypoint.sh:
  1. `python manage.py collectstatic --noinput` を毎回実行
  2. `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 60`
- collectstatic を entrypoint に分離することで、ビルド時の環境依存（DB接続等）を回避

### 3. config/settings.py

#### WhiteNoise

- `MIDDLEWARE` に `whitenoise.middleware.WhiteNoiseMiddleware` を `SecurityMiddleware` 直後に追加
- `STATIC_ROOT = BASE_DIR / "staticfiles"` を設定
- `STORAGES` で `CompressedManifestStaticFilesStorage` を指定（gzip + ハッシュ付きファイル名）

#### CORS 環境変数対応

- `DJANGO_CORS_ALLOWED_ORIGINS` 環境変数（カンマ区切り）で上書き可能
- 未設定時はローカル開発用デフォルト（`http://localhost:5173`, `http://127.0.0.1:5173`）を維持

#### CSRF_TRUSTED_ORIGINS

- `DJANGO_CSRF_TRUSTED_ORIGINS` 環境変数（カンマ区切り）で設定
- 未設定時は空リスト（Django デフォルト動作）

#### 既存維持

- `DEBUG` → `DJANGO_DEBUG` 環境変数（既存通り）
- `ALLOWED_HOSTS` → `DJANGO_ALLOWED_HOSTS` 環境変数（既存通り）

### 4. /healthz エンドポイント

- 既存の `health` ビュー（`{"ok": true, "service": "roomink"}`）を `/healthz` パスにも追加
- 認証不要（ビュー関数は DRF 外で定義済み）
- App Runner のヘルスチェックパスとして使用

## 環境変数一覧（本番設定）

| 変数名 | 必須 | 例 | 説明 |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | `<ランダム文字列>` | Django SECRET_KEY |
| `DJANGO_DEBUG` | No | `0` | 本番では `0` |
| `DJANGO_ALLOWED_HOSTS` | No | `app.example.com,*.awsapprunner.com` | カンマ区切り |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | No | `https://app.example.com` | カンマ区切り |
| `DJANGO_CORS_ALLOWED_ORIGINS` | No | `https://app.example.com` | カンマ区切り |
| `USE_POSTGRES` | Yes | `1` | Postgres 使用 |
| `POSTGRES_DB` | Yes | `roomink` | DB名 |
| `POSTGRES_USER` | Yes | `roomink` | DBユーザー |
| `POSTGRES_PASSWORD` | Yes | `<password>` | DBパスワード |
| `POSTGRES_HOST` | Yes | `<RDS endpoint>` | DBホスト |
| `POSTGRES_PORT` | No | `5432` | DBポート |

## ローカル互換

- Docker Compose + Vite proxy の動作に影響なし
- entrypoint.sh は collectstatic → gunicorn を実行するが、ローカルでは compose.yml 経由で同じように動く
- Session認証・既存API は一切変更なし

## App Runner デプロイ時の設定

```
ヘルスチェックパス: /healthz
ポート: 8000
```

## テスト手順（手動）

### ローカル確認
1. `docker compose build && docker compose up` で起動
2. `curl http://localhost:8000/healthz` → `{"ok": true, "service": "roomink"}`
3. フロントエンドから既存機能が正常動作すること

### 本番確認
4. App Runner でデプロイ
5. ヘルスチェック `/healthz` が 200 を返すこと
6. Django Admin の CSS が表示されること（WhiteNoise 動作確認）
7. API が正常に動作すること
