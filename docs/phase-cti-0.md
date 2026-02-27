# Phase CTI-0 — Webhook 着信 → store 判定 → CallLog 化 → 運営キュー

## 概要

CTI（Computer Telephony Integration）の第 0 フェーズ。
外部 CTI サービスからの Webhook で着信を受け取り、`to_phone`（着信先番号）で店舗を判定し、`CallLog` を作成。
運営ダッシュボードで未対応コールをリアルタイム表示し、クリックで電話予約画面に遷移する。

## 追加モデル

### StorePhoneNumber

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `store` | FK → Store | 店舗 |
| `phone` | CharField(20), unique | 店舗の電話番号（正規化済み） |
| `label` | CharField(50), blank | ラベル（「代表」「予約専用」等） |

### CallLog

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `store` | FK → Store | 着信先店舗 |
| `contact_id` | CharField(128), unique | CTI 側の通話 ID（upsert キー） |
| `from_phone` | CharField(20) | 発信元番号（正規化済み） |
| `to_phone` | CharField(20) | 着信先番号（正規化済み） |
| `status` | NEW / IN_PROGRESS / DONE / MISSED | 対応ステータス |
| `assigned_to` | FK → User, null | 対応担当者 |
| `customer` | FK → Customer, null | 発信元番号で特定された顧客 |
| `is_repeat` | bool | 同一 store + from_phone で直近 10 分以内に別の CallLog がある |
| `created_at` | auto | 作成日時 |
| `updated_at` | auto | 更新日時 |

### CallNote

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `call` | FK → CallLog | 対象コール |
| `author` | FK → User | 記入者 |
| `body` | TextField | メモ本文 |
| `created_at` | auto | 作成日時 |

マイグレーション:
- `core/migrations/0005_cti_models.py` — モデル作成
- `core/migrations/0006_cti_index_update.py` — CallLog index を `(store, status, created_at)` に拡張

## to_phone → store 判定仕様

1. Webhook の `to_phone` を `normalize_phone()` で正規化
2. `StorePhoneNumber.objects.get(phone=to_phone)` で店舗を特定
3. 該当なし → 422 エラー

## 電話番号正規化仕様

`core/utils/phone.py` の `normalize_phone()`:

1. 数字以外をすべて除去
2. +81 携帯番号を国内形式に戻す:
   - `8190...` → `090...`
   - `8180...` → `080...`
   - `8170...` → `070...`

### 具体例

| 入力 | 出力 |
|------|------|
| `+81-90-1234-5678` | `09012345678` |
| `090-1234-5678` | `09012345678` |
| `+818012345678` | `08012345678` |
| `03-1234-5678` | `0312345678` |
| `(空)` | `(空)` |

## API 一覧

### POST /api/op/cti/inbound/（Webhook 受信）

**認証**: `X-CTI-TOKEN` ヘッダーのみ（環境変数 `CTI_SHARED_TOKEN`、無ければ `dev-token`）。
`authentication_classes = []` / `permission_classes = [AllowAny]` で DRF SessionAuth/CSRF を無効化。

**リクエスト**:
```json
{
  "contact_id": "call-uuid-123",
  "from_phone": "+81-90-1234-5678",
  "to_phone": "03-1234-5678"
}
```

**レスポンス** (201/200):
```json
{
  "id": 1,
  "contact_id": "call-uuid-123",
  "store_id": 1,
  "store_name": "渋谷店",
  "from_phone": "09012345678",
  "customer_id": 5,
  "customer_name": "田中太郎",
  "is_repeat": false,
  "status": "NEW",
  "created": true
}
```

**エラー**:
- 403: 無効なトークン
- 400: 必須パラメータ不足
- 422: 着信先番号に対応する店舗が見つからない

### GET /api/op/cti/queue/（未対応コール一覧）

**認証**: login 必須

**レスポンス**:
```json
{
  "calls": [
    {
      "id": 1,
      "contact_id": "call-uuid-123",
      "store_id": 1,
      "store_name": "渋谷店",
      "from_phone": "09012345678",
      "to_phone": "0312345678",
      "customer_id": 5,
      "customer_name": "田中太郎",
      "is_repeat": false,
      "status": "NEW",
      "assigned_to": null,
      "created_at": "2026-02-27T15:00:00+09:00",
      "updated_at": "2026-02-27T15:00:00+09:00"
    }
  ]
}
```

### POST /api/op/cti/calls/{id}/start/（対応開始）

**認証**: login 必須

ステータスを `IN_PROGRESS` に変更し、`assigned_to` に操作者を設定。

### POST /api/op/cti/calls/{id}/done/（対応完了）

**認証**: login 必須

ステータスを `DONE` に変更。

### POST /api/op/cti/calls/{id}/notes/（メモ追加）

**認証**: login 必須

**リクエスト**:
```json
{ "body": "折返し希望。17時以降" }
```

**レスポンス** (201):
```json
{
  "id": 1,
  "call_id": 1,
  "author": "admin",
  "body": "折返し希望。17時以降",
  "created_at": "2026-02-27T15:05:00+09:00"
}
```

## フロントエンド変更

### 運営ダッシュボード (`Dashboard.vue`)

- 統計カードの上に「未対応コール」カード追加
- 2 秒ポーリングで `/api/op/cti/queue/` を取得
- NEW 件数バッジ、最新 5 件表示、再着信バッジ
- 「対応」ボタンクリックで `/op/phone?phone=<from_phone>` に遷移

### 電話予約画面 (`Phone.vue`)

- `?phone=<number>` クエリパラメータ対応
- 顧客一覧から一致する電話番号を自動選択
- 該当なしの場合は警告メッセージ表示

### API クライアント (`api.js`)

追加メソッド:
- `getCtiQueue()` — GET /api/op/cti/queue/
- `ctiCallStart(id)` — POST /api/op/cti/calls/{id}/start/
- `ctiCallDone(id)` — POST /api/op/cti/calls/{id}/done/
- `ctiCallAddNote(id, body)` — POST /api/op/cti/calls/{id}/notes/

## IsAuthenticated 明示（前提修正）

顧客系 View (`/api/cu/*`) はすべて `permission_classes = [IsAuthenticated]` を明示的に設定。
`DEFAULT_PERMISSION_CLASSES` に依存しない事故耐性の強化。

対象:
- `CustomerStoresView`
- `CustomerMypageView`
- `CustomerBookingOptionsView`
- `CustomerBookingCreateView`

## Django Admin 登録

`core/admin.py` に全モデルを登録済み。CTI 関連:
- `StorePhoneNumber` — 店舗電話番号の GUI 管理
- `CallLog` — コール一覧 + CallNote インライン表示
- `CallNote` — メモ単体管理

## StorePhoneNumber 登録例

### Django shell

```python
from core.models import Store, StorePhoneNumber
store = Store.objects.get(name="渋谷店")
StorePhoneNumber.objects.create(store=store, phone="0312345678", label="代表")
```

### Django Admin

`StorePhoneNumber` は admin に登録すれば GUI から管理可能。

## 動作確認手順

### 1. StorePhoneNumber 登録

```bash
python manage.py shell -c "
from core.models import Store, StorePhoneNumber
store = Store.objects.first()
StorePhoneNumber.objects.get_or_create(store=store, phone='0312345678', defaults={'label': '代表'})
print('OK:', store.name, '→ 0312345678')
"
```

### 2. Webhook 着信テスト

```bash
curl -s -X POST http://127.0.0.1:8000/api/op/cti/inbound/ \
  -H 'Content-Type: application/json' \
  -H 'X-CTI-TOKEN: dev-token' \
  -d '{"contact_id":"test-001","from_phone":"+81-90-1234-5678","to_phone":"03-1234-5678"}'
# → 201 {"id":1,"contact_id":"test-001","store_id":1,...,"status":"NEW","created":true}
```

### 3. 存在しない着信先 → 422

```bash
curl -s -X POST http://127.0.0.1:8000/api/op/cti/inbound/ \
  -H 'Content-Type: application/json' \
  -H 'X-CTI-TOKEN: dev-token' \
  -d '{"contact_id":"test-002","from_phone":"09000000000","to_phone":"09999999999"}'
# → 422 {"detail":"着信先番号 09999999999 に対応する店舗が見つかりません"}
```

### 4. 無効トークン → 403

```bash
curl -s -X POST http://127.0.0.1:8000/api/op/cti/inbound/ \
  -H 'Content-Type: application/json' \
  -H 'X-CTI-TOKEN: wrong-token' \
  -d '{"contact_id":"test-003","from_phone":"09000000000","to_phone":"0312345678"}'
# → 403 {"detail":"無効なトークンです"}
```

### 5. キュー取得

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/api/op/cti/queue/
# → {"calls":[{"id":1,"contact_id":"test-001","status":"NEW",...}]}
```

### 6. 対応開始

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/op/cti/calls/1/start/
# → {"id":1,"status":"IN_PROGRESS"}
```

### 7. メモ追加

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/op/cti/calls/1/notes/ \
  -H 'Content-Type: application/json' \
  -d '{"body":"折返し希望"}'
# → 201 {"id":1,"call_id":1,"author":"admin","body":"折返し希望",...}
```

### 8. 対応完了

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/op/cti/calls/1/done/
# → {"id":1,"status":"DONE"}
```

### 9. フロントエンド確認

1. `/op/dashboard` にアクセス — 未対応コールがあればカード表示（2 秒自動更新）
2. 「対応」ボタンクリック → `/op/phone?phone=09012345678` に遷移
3. 該当顧客があれば自動選択、なければ警告メッセージ
