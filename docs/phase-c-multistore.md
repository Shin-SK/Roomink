# Phase C — 多店舗対応（顧客UI）

## 概要

1 ユーザーが複数店舗の Customer を持てるようにし、顧客 UI にサイドドロワーで店舗切替を追加。

## モデル変更

| 変更 | Before | After |
|------|--------|-------|
| `Customer.user` | `OneToOneField` | `ForeignKey`（1 User → 複数 Customer） |
| `related_name` | `customer_profile` | `customer_profiles` |

マイグレーション: `core/migrations/0004_customer_user_fk.py`

## 共通顧客解決関数 `resolve_customer`

**場所**: `core/services/customer_context.py`

**前提**: ログイン済みであること（未ログインは DRF の `IsAuthenticated` が 403 を返す）。
`resolve_customer` はログイン済み前提で Customer を解決する責務のみ持つ。

顧客系 API は **すべて** この関数を通して Customer を取得する。
`request.user.customer_profile` / `customer_profiles` の直接参照は禁止。
顧客系 View で `resolve_customer` 以外から Customer を触ることも禁止。

```python
from core.services.customer_context import resolve_customer

customer = resolve_customer(request)  # Customer or 例外
```

### ルール

| 条件 | 結果 |
|------|------|
| 未ログイン | DRF `IsAuthenticated` が 403（resolve_customer の責務外） |
| Customer 0 件 | `PermissionDenied` (403)「顧客プロフィールが紐づいていません」 |
| `?store=<ID>` 指定 → 該当あり | その Customer を返す |
| `?store=<ID>` 指定 → 該当なし | `PermissionDenied` (403)「指定された店舗に所属していません」 |
| store 未指定 & 所属 1 店舗 | 自動選択 |
| store 未指定 & 複数店舗 | `ValidationError` (400)「複数店舗に所属しています。store パラメータを指定してください」 |

### 影響範囲

以下の API は `resolve_customer` 必須:

- `GET /api/cu/mypage/`
- `GET /api/cu/booking/options/`
- `POST /api/cu/bookings/`

`GET /api/cu/stores/` は全店舗一覧を返すため `resolve_customer` は使わず
`Customer.objects.filter(user=request.user)` を直接使用。

## 新規 API

### GET /api/cu/stores/

ログインユーザーに紐づく Customer の店舗一覧を返す。

**認証**: login 必須

**レスポンス**:
```json
{
  "stores": [
    {"store_id": 1, "store_name": "渋谷店", "logo_url": ""},
    {"store_id": 2, "store_name": "新宿店", "logo_url": ""}
  ]
}
```

**エラー**:
- 403: 顧客プロフィールが紐づいていない

## 既存 API 変更

以下の 3 エンドポイントに `?store=<ID>` クエリパラメータを追加。

| エンドポイント | メソッド | store パラメータ挙動 |
|---------------|---------|---------------------|
| `/api/cu/mypage/` | GET | store 指定 → その store の Customer を使用 |
| `/api/cu/booking/options/` | GET | 同上 |
| `/api/cu/bookings/` | POST | 同上 |

## フロントエンド

### 店舗切替ドロワー

- `customer-header` 内に店舗ボタン（店名 + chevron）を追加
- 複数店舗の場合のみ表示
- クリックでサイドドロワーが左からスライドイン
- 店舗リスト: アイコン（丸）＋ 店名、選択中はハイライト
- 選択 → `?store=<ID>` 付きでページ遷移

### 対象ページ

| ページ | ファイル | 変更内容 |
|-------|---------|---------|
| マイページ | `CuMypage.vue` | ドロワー追加、API に store param 送信、ナビリンクに store 引き回し |
| 予約フォーム | `CuBooking.vue` | 同上 |
| 予約完了 | `CuSubmitted.vue` | リンクに store param 引き回し |
| API クライアント | `api.js` | `getCustomerStores` 追加、既存 3 メソッドに storeId 引数追加 |

### 追加 CSS

`_customer.scss` 末尾に追加:
- `.rk-store-btn` — ヘッダー内の店舗切替ボタン
- `.rk-store-overlay` — 半透明オーバーレイ
- `.rk-store-drawer` — 左サイドドロワー本体

## 動作確認手順

### 1. 店舗一覧取得

```bash
curl -s -b cookies.txt http://127.0.0.1:8000/api/cu/stores/
# → {"stores": [{"store_id": 1, "store_name": "...", "logo_url": ""}]}
```

### 2. store 指定でマイページ取得

```bash
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/cu/mypage/?store=1'
# → 通常の mypage レスポンス
```

### 3. 存在しない store 指定 → 403

```bash
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/cu/mypage/?store=999'
# → 403 {"detail": "指定された店舗に所属していません"}
```

### 4. 複数店舗 & store 未指定 → 400

```bash
# (ユーザーが複数店舗に所属している場合)
curl -s -b cookies.txt http://127.0.0.1:8000/api/cu/mypage/
# → 400 {"detail": "複数店舗に所属しています。store パラメータを指定してください"}
```

### 5. 予約オプション（store 指定）

```bash
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/cu/booking/options/?store=1'
# → {"casts": [...], "courses": [...], "options": [...]}
```

### 6. 予約申請（store 指定）

```bash
curl -s -b cookies.txt -X POST 'http://127.0.0.1:8000/api/cu/bookings/?store=1' \
  -H 'Content-Type: application/json' \
  -d '{"cast":1,"course":1,"start":"2026-03-01T15:00:00+09:00"}'
# → 201 Order レスポンス
```

### 7. フロントエンド確認

1. `/cu/mypage` にアクセス — 1 店舗ならそのまま表示
2. 複数店舗の場合、ヘッダーに店舗名ボタンが表示される
3. ボタンクリックでサイドドロワーが開き、店舗リストが表示される
4. 店舗をタップすると `?store=ID` 付きで遷移し、データが切り替わる
5. 予約フォーム・完了画面でも store が引き回される
