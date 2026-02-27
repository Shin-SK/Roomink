# Phase C — 顧客マイページ＋Web予約申請MVP

## 概要

顧客が「マイページ」で予約状況・来店履歴を確認し、「Web予約申請」から予約リクエストを送信できる機能を実装。
電話予約→マイページ誘導の土台。

| 項目 | 内容 |
|------|------|
| 実施日 | 2026-02-27 |
| 前提 | Phase A/B 完了済み |

---

## ログイン方式

- Django User の `username` に電話番号を格納する運用
- Customer.user（OneToOneField）で紐づけ
- 認証は Phase A の `/api/auth/login/` をそのまま使用（Session認証）
- 初回登録は `/api/cu/signup/` で User + Customer を同時作成

---

## C-1: Backend（顧客アカウント）

### Customer.user 紐づけ

`core/models.py` に追加:

```python
Customer.user = OneToOneField(User, null=True, blank=True, on_delete=SET_NULL, related_name="customer_profile")
```

- migration: `core/migrations/0003_customer_user_link.py`
- 運営が Django admin で Customer レコードの `user` フィールドにユーザーを紐づける運用も可

### 顧客登録API

| メソッド | URL | 認証 | 説明 |
|----------|-----|------|------|
| POST | `/api/cu/signup/` | 不要 | 顧客アカウント新規作成 |

#### POST /api/cu/signup/ リクエスト

```json
{
  "phone": "080-1234-5678",
  "password": "mypassword",
  "display_name": "田中太郎"
}
```

#### レスポンス

- 成功（201）: `{"ok": true, "username": "080-1234-5678"}`
- 電話番号重複（409）: `{"detail": "この電話番号は既に登録されています"}`
- 既存 Customer に user が既に紐づいている場合も 409

---

## C-2: Backend（顧客マイページ）

### GET /api/cu/mypage/

| メソッド | URL | 認証 | 説明 |
|----------|-----|------|------|
| GET | `/api/cu/mypage/` | 必要 | 顧客マイページ情報 |

#### レスポンス

```json
{
  "customer": {
    "display_name": "田中太郎",
    "phone": "080-1234-5678",
    "total_visits": 5,
    "total_spend": 92000
  },
  "next_reservation": {
    "id": 1,
    "start": "2026-02-28T13:00:00+09:00",
    "end": "2026-02-28T14:30:00+09:00",
    "status": "CONFIRMED",
    "cast_name": "あやか",
    "course_name": "90分コース",
    "total_price": 18000
  },
  "favorites": [
    {
      "id": 1,
      "name": "あやか",
      "avatar_url": "",
      "visit_count": 4,
      "total_spend": 74000
    }
  ],
  "recommended": [
    {"id": 2, "name": "みさき", "avatar_url": ""},
    {"id": 3, "name": "ゆい", "avatar_url": ""}
  ],
  "history": [
    {
      "id": 10,
      "date": "2026-01-15",
      "cast_name": "あやか",
      "course_name": "90分コース",
      "total_price": 18000,
      "status": "DONE"
    }
  ]
}
```

#### 権限チェック

- ログインユーザーに `customer_profile` が紐づいていない → 403

---

## C-3: Backend（顧客の予約申請）

### GET /api/cu/booking/options/

| メソッド | URL | 認証 | 説明 |
|----------|-----|------|------|
| GET | `/api/cu/booking/options/` | 必要 | 予約フォーム選択肢 |

#### レスポンス

```json
{
  "casts": [{"id": 1, "name": "あやか", "avatar_url": ""}],
  "courses": [{"id": 1, "name": "90分コース", "duration": 90, "price": 18000}],
  "options": [{"id": 1, "name": "アロマオイル", "price": 2000}]
}
```

### POST /api/cu/bookings/

| メソッド | URL | 認証 | 説明 |
|----------|-----|------|------|
| POST | `/api/cu/bookings/` | 必要 | 予約申請（REQUESTED） |

#### リクエスト

```json
{
  "cast": 1,
  "course": 1,
  "start": "2026-02-28T15:00:00+09:00",
  "options": [1, 2],
  "memo": "駐車場利用希望"
}
```

- `customer` はログインユーザーの `customer_profile` を自動使用（フロントから送信不要）
- 既存の `OrderCreateSerializer` のロジック（end自動算出・room自動確定・競合チェック）を再利用
- status は `REQUESTED` で作成

#### レスポンス

成功時: 作成した Order オブジェクト（OrderSerializer）

---

## C-4: Frontend

### ルーティング

| パス | コンポーネント | 説明 |
|------|---------------|------|
| `/cu/mypage` | `CuMypage.vue` | 顧客マイページ |
| `/cu/booking` | `CuBooking.vue` | 予約申請フォーム |
| `/cu/submitted` | `CuSubmitted.vue` | 申請完了画面 |

### 顧客マイページ（/cu/mypage）

モック `HTML/cu_mypage.html` 準拠:
- `customer-layout` / `customer-header` / `customer-content` の DOM 構造
- あいさつ（「こんにちは、○○様」）
- 予約カード（`rk-booking-card` グラデーション / 予約なし時は `--empty`）
- タブUI（推し / おすすめ / 運営）
  - 推し: `rk-fav-card` 大きめカード
  - おすすめ: `rk-hscroll` 横スクロール
  - 運営: `rk-campaign` カード
- 来店履歴（`rk-history-item`）
- 登録情報テーブル
- Bottom Nav（HOME / 予約 / 推し / 問い合わせ）

### 予約申請ページ（/cu/booking）

モック `HTML/cu_booking.html` 準拠:
- 予約日・希望時間
- セラピスト指名（select）
- コース選択（radio）
- オプション（checkbox）
- 備考テキストエリア
- 注意事項（alert-info）
- 送信ボタン → POST /api/cu/bookings/ → /cu/submitted に遷移

### 申請完了（/cu/submitted）

モック `HTML/cu_submitted.html` 準拠:
- 成功アイコン（チェックマーク円形）
- 申請内容カード（担当/日時/コース/料金/ステータス）
- 次のステップ説明
- SMS通知案内
- アクションボタン（マイページ / 別の予約）

---

## 変更ファイル一覧

### 新規作成

| ファイル | 説明 |
|----------|------|
| `core/migrations/0003_customer_user_link.py` | Customer.user フィールド追加 |
| `frontend/src/pages/cu/CuMypage.vue` | 顧客マイページ |
| `frontend/src/pages/cu/CuBooking.vue` | 予約申請フォーム |
| `frontend/src/pages/cu/CuSubmitted.vue` | 申請完了画面 |
| `docs/phase-c-customer.md` | 本ドキュメント |

### 変更

| ファイル | 変更内容 |
|----------|----------|
| `core/models.py` | Customer に `user` OneToOneField 追加 |
| `core/views.py` | customer_signup, CustomerMypageView, CustomerBookingOptionsView, CustomerBookingCreateView 追加 |
| `core/urls.py` | `cu/signup/`, `cu/mypage/`, `cu/booking/options/`, `cu/bookings/` 追加 |
| `frontend/src/api.js` | customerSignup, getCustomerMypage, getBookingOptions, createCustomerBooking 追加 |
| `frontend/src/router.js` | `/cu/mypage`, `/cu/booking`, `/cu/submitted` ルート追加 |

---

## 動作確認手順

### 1. 顧客ユーザー作成（signup API）

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/cu/signup/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"080-1234-5678","password":"cust1234","display_name":"田中太郎"}'
# → {"ok": true, "username": "080-1234-5678"}
```

### 2. 顧客ログイン（既存 auth API）

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"080-1234-5678","password":"cust1234"}'
```

### 3. マイページ取得

```bash
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/cu/mypage/' | python -m json.tool
# → customer, next_reservation, favorites, recommended, history
```

### 4. 予約フォーム選択肢取得

```bash
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/cu/booking/options/' | python -m json.tool
# → casts, courses, options
```

### 5. 予約申請

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/cu/bookings/ \
  -H 'Content-Type: application/json' \
  -d '{"cast":1,"course":1,"start":"2026-02-28T15:00:00+09:00","options":[],"memo":"テスト予約"}'
# → Order オブジェクト（status: REQUESTED）
```

### 6. 運営 Schedule で REQUESTED 確認

```bash
curl -s -b admin_cookies.txt 'http://127.0.0.1:8000/api/op/schedule/?date=2026-02-28' | python -m json.tool
# → orders[].status === "REQUESTED" の予約が出る
```

### 7. フロントエンド確認

1. 顧客 signup（上記 curl）→ ログイン
2. http://localhost:5173/cu/mypage にアクセス → マイページ表示
3. http://localhost:5173/cu/booking にアクセス → 予約フォーム
4. セラピスト・コース・日時を選択して「予約を申請」
5. /cu/submitted に遷移 → 申請内容表示
6. 運営 http://localhost:5173/op/schedule で REQUESTED 予約確認

---

## モック対応表

| モックファイル | Vue コンポーネント | 対応 |
|---------------|-------------------|------|
| `HTML/cu_mypage.html` | `CuMypage.vue` | DOM構造・CSS class 完全一致 |
| `HTML/cu_booking.html` | `CuBooking.vue` | DOM構造・CSS class 完全一致 |
| `HTML/cu_submitted.html` | `CuSubmitted.vue` | DOM構造・CSS class 完全一致 |
