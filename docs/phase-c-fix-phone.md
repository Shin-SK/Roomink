# Phase C — 電話番号正規化

## 正規化ルール

- 数字以外をすべて除去して保存・比較する
  - 例: `"080-1234-5678"` → `"08012345678"`
- 空文字 / None はそのまま（バリデーションは既存に任せる）
- 先頭 `+` や国際番号対応は今回スコープ外

## 正規化関数

`core/utils/phone.py` の `normalize_phone(phone: str) -> str` に集約。

## 適用箇所

| 箇所 | ファイル | 詳細 |
|------|----------|------|
| 顧客 signup API | `core/views.py` `customer_signup()` | phone を正規化後に User.username / Customer.phone にセット。重複チェックも正規化後 |
| ログイン API | `core/views.py` `auth_login()` | username を正規化してから authenticate（ハイフン付きでもログイン可） |
| CSV import | `core/views.py` `_upsert_rows()` | customer の phone を正規化して upsert キーに使用 |
| CustomerSerializer | `core/serializers.py` | `validate_phone()` で正規化。CustomerViewSet 経由の create/update すべてに適用 |

## 動作確認手順

### 1. signup（ハイフン付き → 正規化保存）

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/cu/signup/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"080-1234-5678","password":"cust1234","display_name":"田中太郎"}'
# → {"ok": true, "username": "08012345678"}
```

### 2. 重複チェック（ハイフンなしで再登録 → 409）

```bash
curl -s -X POST http://127.0.0.1:8000/api/cu/signup/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"08012345678","password":"cust1234","display_name":"田中太郎"}'
# → 409 {"detail": "この電話番号は既に登録されています"}
```

### 3. ログイン（ハイフン付きでも可）

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"080-1234-5678","password":"cust1234"}'
# → {"ok": true, "username": "08012345678"}
```

### 4. CSV import（ハイフン付き → 正規化保存）

customers.csv:
```csv
phone,display_name,flag,memo
090-1234-5678,山田花子,NONE,テスト
```

```bash
curl -s -b admin_cookies.txt -X POST \
  'http://127.0.0.1:8000/api/op/csv-import/?model=customer' \
  -F file=@customers.csv
# → DB には phone="09012345678" で保存
```

### 5. CustomerViewSet 経由の更新

```bash
curl -s -b admin_cookies.txt -X PATCH http://127.0.0.1:8000/api/customers/1/ \
  -H 'Content-Type: application/json' \
  -d '{"phone":"070-9876-5432"}'
# → phone が "07098765432" で保存される
```
