# Phase B — キャスト運用MVP

## 概要

キャストが「本日の予約」を閲覧し、各予約を「確認（ACK）」できる機能を実装。
運営側 Schedule でも未確認状態が可視化される。

| 項目 | 内容 |
|------|------|
| 実施日 | 2026-02-27 |
| 前提 | Phase A 完了済み |

---

## B-1: Backend

### Cast.user 紐づけ

`core/models.py` に追加:

```python
Cast.user = OneToOneField(User, null=True, blank=True, on_delete=SET_NULL, related_name="cast_profile")
```

- migration: `core/migrations/0002_cast_user_link.py`
- 運営が Django admin で Cast レコードの `user` フィールドにユーザーを紐づける運用

### Cast 用 API

| メソッド | URL | 認証 | 説明 |
|----------|-----|------|------|
| GET | `/api/cast/today/?date=YYYY-MM-DD` | 必要 | 自分のキャストの当日予約一覧 |
| POST | `/api/cast/orders/{id}/ack/` | 必要 | 予約を確認（ACK） |

#### GET /api/cast/today/ レスポンス

```json
{
  "cast_name": "あかり",
  "avatar_url": "",
  "date": "2026-02-27",
  "shift": {
    "start_time": "12:00",
    "end_time": "20:00",
    "room_name": "Room A"
  },
  "total_orders": 2,
  "unconfirmed_count": 1,
  "orders": [
    {
      "id": 1,
      "start": "2026-02-27T13:00:00+09:00",
      "end": "2026-02-27T14:30:00+09:00",
      "status": "CONFIRMED",
      "room_id": 1,
      "room_name": "Room A",
      "customer_label": "田中太郎",
      "course_name": "90分コース",
      "course_price": 12000,
      "memo": "駐車場利用希望",
      "is_unconfirmed": false
    }
  ]
}
```

#### POST /api/cast/orders/{id}/ack/ レスポンス

更新後の Order オブジェクト（`is_unconfirmed: false`）を返す。

#### 権限チェック

- ログインユーザーに `cast_profile` が紐づいていない → 403
- 別キャストの予約を ACK しようとした → 403

### Schedule API 拡張

`/api/op/schedule/` の `orders[]` に `is_unconfirmed: boolean` を追加。

- CastAck レコードが存在し `acked_at` が非 null → `false`（確認済）
- それ以外 → `true`（未確認）

---

## B-2: Frontend

### /cast/today ページ

`frontend/src/pages/cast/CastToday.vue`

モック `HTML/ca_mypage.html` に完全一致で実装:
- `cast-layout` / `cast-header` / `cast-content` の DOM 構造
- ページヘッダー（アバター + 名前 + シフト時間/ルーム）
- サマリーカード 2 列（本日の予約 / 未確認）
- 未確認警告カード（`alert-warning`）
- 予約カード一覧
  - 確認済: `badge-approved` + disabled ボタン
  - 未確認: `border-warning border-2` + `badge-unconfirmed` + 「確認する」ボタン
- タイムライン（`ca-schedule` + `rk-sheet` 1 カラム）
  - 未確認ブロック: `is-unconfirmed` class（`!` バッジ表示）
- 注意事項（collapse）
- 運営電話リンク
- フッター（マイページ / 予約リスト / タイムライン）

### 運営 Schedule 未確認バッジ

`TimelineGrid.vue` の `statusClass()` に `is_unconfirmed` 対応を追加。

- `order.is_unconfirmed === true` → `is-unconfirmed` class 付与
- CSS（既存）: `.rk-block.is-unconfirmed::after` で `!` バッジ表示

---

## 変更ファイル一覧

### 新規作成

| ファイル | 説明 |
|----------|------|
| `core/migrations/0002_cast_user_link.py` | Cast.user フィールド追加 |
| `frontend/src/pages/cast/CastToday.vue` | キャスト本日予約ページ |
| `docs/phase-b-cast.md` | 本ドキュメント |

### 変更

| ファイル | 変更内容 |
|----------|----------|
| `core/models.py` | Cast に `user` OneToOneField 追加 |
| `core/views.py` | CastTodayView, CastAckView 追加 |
| `core/serializers.py` | CastTodayOrderSerializer 追加、ScheduleOrderSerializer に is_unconfirmed 追加、build_schedule_data に CastAck ルックアップ追加 |
| `core/urls.py` | `cast/today/`, `cast/orders/<pk>/ack/` 追加 |
| `frontend/src/api.js` | getCastToday, ackOrder 追加 |
| `frontend/src/router.js` | `/cast/today` ルート追加 |
| `frontend/src/components/TimelineGrid.vue` | statusClass に is_unconfirmed 対応追加 |

---

## 動作確認手順

### 1. キャストユーザー作成・紐づけ

```bash
# ユーザー作成
python manage.py shell -c "
from django.contrib.auth.models import User
u = User.objects.create_user('cast_akari', password='cast1234')
print(f'User created: {u.username} (id={u.id})')
"

# Cast に紐づけ（例: Cast id=1）
python manage.py shell -c "
from django.contrib.auth.models import User
from core.models import Cast
cast = Cast.objects.first()
cast.user = User.objects.get(username='cast_akari')
cast.save()
print(f'Cast {cast.name} linked to user {cast.user.username}')
"
```

### 2. キャストログイン → /cast/today

```bash
# ログイン
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"cast_akari","password":"cast1234"}'

# 当日予約取得
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/cast/today/?date=2026-02-27' | python -m json.tool
```

### 3. ACK（予約確認）

```bash
# 未確認の予約を ACK
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/cast/orders/{ORDER_ID}/ack/ | python -m json.tool
# → is_unconfirmed: false

# 再度 /cast/today を取得 → unconfirmed_count が減っている
curl -s -b cookies.txt 'http://127.0.0.1:8000/api/cast/today/?date=2026-02-27' | python -m json.tool
```

### 4. 別キャストの予約を ACK → 403

```bash
# 別キャストの予約 ID を指定
curl -s -b cookies.txt -X POST http://127.0.0.1:8000/api/cast/orders/{OTHER_ORDER_ID}/ack/
# → {"detail":"この予約は別のキャストに割り当てられています"}
```

### 5. 運営 Schedule で未確認確認

```bash
# 運営ユーザーでログイン
curl -s -c admin_cookies.txt -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'

# Schedule 取得 → orders[].is_unconfirmed を確認
curl -s -b admin_cookies.txt 'http://127.0.0.1:8000/api/op/schedule/?date=2026-02-27' | python -m json.tool
# → ACK 済みの予約は is_unconfirmed: false、未 ACK は true
```

### 6. フロントエンド確認

1. キャストユーザーで Django admin にログイン
2. http://localhost:5173/cast/today にアクセス
3. 予約カードが表示される（未確認は黄色ボーダー + 「未確認」バッジ）
4. 「確認する」ボタンクリック → 即時 UI 更新（「確認済」に変わる）
5. 運営ユーザーで http://localhost:5173/op/schedule にアクセス
6. タイムラインで ACK 前は `!` バッジ表示、ACK 後は消える
