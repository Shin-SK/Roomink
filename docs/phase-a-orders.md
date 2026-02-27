# Phase A — 予約 CRUD・通知・CSV Import・認証

## 概要

Roomink MVP を「運営が ShopManage 代替として使える状態」にするための Phase A 実装。

| 項目 | 内容 |
|------|------|
| 実施日 | 2026-02-27 |
| 対象 | backend (Django+DRF) / frontend (Vue 3) |
| ブランチ | (未コミット — diff で確認) |

---

## A-1: 予約ステータス操作

### 追加エンドポイント

| メソッド | URL | 説明 |
|----------|-----|------|
| POST | `/api/orders/{id}/confirm/` | REQUESTED → CONFIRMED |
| POST | `/api/orders/{id}/cancel/` | REQUESTED/CONFIRMED/IN_PROGRESS → CANCELLED |
| POST | `/api/orders/{id}/done/` | CONFIRMED/IN_PROGRESS → DONE |

### ステータス遷移図

```
REQUESTED ──confirm──→ CONFIRMED ──(手動)──→ IN_PROGRESS
    │                      │                      │
    │                      │                      │
    └───cancel───→ CANCELLED ←───cancel────────────┘
                           │
                  CONFIRMED/IN_PROGRESS ──done──→ DONE
```

### バリデーション

- `confirm`: status が REQUESTED のときのみ許可
- `cancel`: status が DONE / CANCELLED のときは拒否
- `done`: status が CONFIRMED / IN_PROGRESS のときのみ許可

### フロントエンド

`OrderDetail.vue` の承認/キャンセル/完了ボタンを実装済み。
- ステータスに応じてボタンの有効/無効が切り替わる
- confirm() で確認ダイアログ表示後に API を呼ぶ
- 成功時は order オブジェクトを API レスポンスで上書き（画面即時反映）

---

## A-2: 通知サービス層

### ファイル

`core/services/notify.py`

### 設計

```
views.py (confirm/cancel action)
    ↓
services/notify.py
    ├─ notify_order_confirmed(order)  → 顧客 SMS + キャスト SMS
    ├─ notify_order_cancelled(order)  → 顧客 SMS
    └─ send_sms(to, body, order)     → SmsLog 記録（ダミー送信）
```

- 送信ロジックは `send_sms()` に集約。将来 Twilio / LINE に差し替えるときはここだけ修正すればよい
- views / serializers に送信コードは一切なし

### SmsLog 記録タイミング

| イベント | 宛先 | ログ status |
|----------|------|-------------|
| 予約承認 | 顧客 (phone) | SENT |
| 予約承認 | キャスト ("cast") | SENT |
| 予約キャンセル | 顧客 (phone) | SENT |

※ 現時点では実送信せず、SmsLog への INSERT のみ。

---

## A-3: CSV インポート

### エンドポイント

```
POST /api/op/csv-import/?model={model}&preview=1   → プレビュー（先頭10行）
POST /api/op/csv-import/?model={model}              → 実行（upsert）
```

`Content-Type: multipart/form-data` で `file` フィールドに CSV を添付。

### 対応モデル

| model | upsert キー | 必須ヘッダ | 任意ヘッダ |
|-------|-------------|-----------|-----------|
| `room` | (store, name) | name | sort_order |
| `cast` | (store, name) | name | avatar_url |
| `course` | (store, name) | name, duration, price | — |
| `option` | (store, name) | name, price | — |
| `customer` | (store, phone) | phone | display_name, flag, memo |

### CSV フォーマット

- UTF-8（BOM 対応）
- ヘッダ行必須（1行目）
- 空行はスキップ

### サンプル CSV

`docs/csv/` に各モデルのサンプルを配置済み。

#### rooms.csv
```csv
name,sort_order
Room A,1
Room B,2
Room C,3
```

#### casts.csv
```csv
name,avatar_url
あかり,
みさき,
ゆうな,
```

#### courses.csv
```csv
name,duration,price
60分コース,60,8000
90分コース,90,12000
120分コース,120,16000
```

#### options.csv
```csv
name,price
指名料,1000
延長30分,4000
```

#### customers.csv
```csv
phone,display_name,flag,memo
09012345678,田中太郎,NONE,常連
09087654321,山田花子,ATTENTION,要注意顧客
08011112222,佐藤一郎,NONE,
```

### レスポンス例

**プレビュー:**
```json
{
  "model": "room",
  "total_rows": 3,
  "headers": ["name", "sort_order"],
  "preview": [
    {"name": "Room A", "sort_order": "1"},
    {"name": "Room B", "sort_order": "2"}
  ]
}
```

**実行:**
```json
{
  "model": "room",
  "total_rows": 3,
  "created": 2,
  "updated": 1
}
```

---

## A-4: 認証

### 方式

Django Session 認証（DRF の `SessionAuthentication`）。

### 変更点

- 全 ViewSet から `permission_classes = [AllowAny]` を削除
- `settings.py` の `REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES` に `IsAuthenticated` が既に設定済みのため、削除するだけでログイン必須になる
- ログイン用エンドポイントを追加

### 認証エンドポイント

| メソッド | URL | 認証 | 説明 |
|----------|-----|------|------|
| POST | `/api/auth/login/` | 不要 | `{username, password}` → セッション発行 |
| POST | `/api/auth/logout/` | 必要 | セッション破棄 |
| GET | `/api/auth/me/` | 必要 | ログインユーザー情報取得 |

### フロントエンド対応

`api.js` の `request()` に以下を追加:
- `credentials: 'same-origin'` — Cookie を送信
- `X-CSRFToken` ヘッダ — Django CSRF 対応（POST/PATCH/DELETE 時に Cookie から取得）

---

## 変更ファイル一覧

### 新規作成

| ファイル | 説明 |
|----------|------|
| `core/services/__init__.py` | services パッケージ |
| `core/services/notify.py` | 通知サービス層 |
| `docs/phase-a-orders.md` | 本ドキュメント |
| `docs/csv/rooms.csv` | Room サンプル CSV |
| `docs/csv/casts.csv` | Cast サンプル CSV |
| `docs/csv/courses.csv` | Course サンプル CSV |
| `docs/csv/options.csv` | Option サンプル CSV |
| `docs/csv/customers.csv` | Customer サンプル CSV |

### 変更

| ファイル | 変更内容 |
|----------|----------|
| `core/views.py` | OrderViewSet に confirm/cancel/done アクション追加、AllowAny 削除、auth_login/logout/me 追加、CsvImportView 追加 |
| `core/urls.py` | auth/*, op/csv-import/ の URL 追加 |
| `frontend/src/api.js` | CSRF 対応、confirmOrder/cancelOrder/doneOrder/csvPreview/csvImport/login/logout/me 追加 |
| `frontend/src/pages/op/OrderDetail.vue` | 承認/キャンセル/完了ボタンの click ハンドラ実装、状態に応じた disabled 制御 |

---

## 動作確認手順

### 前提

```bash
# backend 起動
cd /path/to/Roomink
python manage.py runserver

# frontend 起動
cd frontend
npm run dev
```

### 1. 管理ユーザー作成（初回のみ）

```bash
python manage.py createsuperuser
```

### 2. ログイン確認

```bash
# 未ログインで 403 になること
curl -s http://127.0.0.1:8000/api/orders/ | python -m json.tool
# → {"detail":"Authentication credentials were not provided."}

# ログイン
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'

# ログイン後は通る
curl -s -b cookies.txt http://127.0.0.1:8000/api/orders/ | python -m json.tool
```

### 3. CSV インポート

```bash
# プレビュー
curl -s -b cookies.txt -X POST \
  'http://127.0.0.1:8000/api/op/csv-import/?model=room&preview=1' \
  -F file=@docs/csv/rooms.csv | python -m json.tool

# 実行
curl -s -b cookies.txt -X POST \
  'http://127.0.0.1:8000/api/op/csv-import/?model=room' \
  -F file=@docs/csv/rooms.csv | python -m json.tool

# 各モデル同様に実行
for m in cast course option customer; do
  curl -s -b cookies.txt -X POST \
    "http://127.0.0.1:8000/api/op/csv-import/?model=$m" \
    -F file=@docs/csv/${m}s.csv | python -m json.tool
done
```

### 4. 予約承認 → SmsLog 確認

```bash
# 予約一覧から REQUESTED の ID を取得
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/orders/?status=REQUESTED' | python -m json.tool

# 承認
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/orders/{ID}/confirm/ | python -m json.tool
# → status: CONFIRMED

# SmsLog 確認（admin で確認 or Django shell）
python manage.py shell -c "from core.models import SmsLog; print(SmsLog.objects.count(), 'logs')"
```

### 5. 予約キャンセル

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/orders/{ID}/cancel/ | python -m json.tool
# → status: CANCELLED
```

### 6. フロントエンド動作確認

1. http://localhost:5173/ にアクセス
2. Django admin (http://127.0.0.1:8000/admin/) でログイン済みなら Cookie が共有される
3. ダッシュボードから承認待ち予約の「詳細」をクリック
4. OrderDetail で「承認」ボタンクリック → ステータスが即時更新される
5. 「キャンセル」ボタンクリック → CANCELLED に変わる
