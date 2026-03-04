# Step6b 実装報告：顧客作成後に Phone へ自動復帰（return導線）

## 概要

Step6 で実装した CTI フロー「顧客未存在 → 顧客作成」の後、手動で Phone に戻る必要があった問題を修正。
`return` クエリパラメータを導入し、顧客作成完了後に自動で `/op/phone?phone=xxx` へ戻って予約作成を継続できるようにした。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `frontend/src/pages/op/Phone.vue` | 変更 | 「この番号で顧客作成」ボタンに `return` パラメータ追加 |
| `frontend/src/pages/op/CustomerDetail.vue` | 変更 | 新規作成成功後、`return` があればそちらへ遷移 |

## 実装詳細

### 1. Phone.vue

- 「この番号で顧客作成」ボタンの遷移先を変更：
  - 旧: `/op/customers/new?phone=<phone>`
  - 新: `/op/customers/new?phone=<phone>&return=/op/phone?phone=<phone>`
- `return` に Phone 自身のURLをセットし、顧客作成後に同じ番号で戻れるようにした

### 2. CustomerDetail.vue

- 新規作成成功後の遷移ロジックを拡張：
  - `route.query.return` が存在し、`/` で始まる内部パスの場合 → `router.replace(return)` で遷移
  - それ以外（未設定、外部URL等）→ 従来通り `/op/customers/:id` へ遷移
- オープンリダイレクト防止：`startsWith('/')` チェックで外部URLを拒否

## 画面フロー（改善後）

```
/op/phone?phone=09012345678
  └ 顧客なし → [この番号で顧客作成]
    ↓ /op/customers/new?phone=09012345678&return=/op/phone?phone=09012345678
    ↓ フォーム入力 → [作成]
    ↓ POST /api/customers/
    ↓ 成功 → router.replace('/op/phone?phone=09012345678')  ← 自動復帰！
    ↓ 顧客が存在するので自動選択 → STEP2（予約作成）
```

## セキュリティ

- `return` パラメータは `/` で始まる内部パスのみ許可
- `http://` や `//` で始まる外部URLは無視され、従来の遷移先にフォールバック

## テスト手順（手動）

1. `/op/phone?phone=未登録番号` で「この番号で顧客作成」をクリック
2. 顧客作成画面で phone が初期入力済みであること
3. フォーム入力 → [作成] → `/op/phone?phone=xxx` に自動で戻ること
4. 戻った Phone 画面で作成した顧客が自動選択されていること
5. `return` なしで `/op/customers/new` から作成 → 従来通り顧客詳細に遷移すること
