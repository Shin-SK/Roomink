# Step3B 実装報告：顧客管理 Step1B（導線＋詳細個別取得）

## 概要

運営UIの顧客管理を「URL直打ち」から「実運用導線」に昇格させた。
サイドバー・フッターに顧客管理リンクを追加し、CustomerDetail を個別API取得に切替。
バックエンド変更なし。既存の `GET /api/customers/:id/` を利用。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `frontend/src/components/LayoutOperator.vue` | 変更 | navItems / footerItems に「顧客管理」リンク追加 |
| `frontend/src/api.js` | 変更 | `getCustomer(id)` 追加（GET /customers/:id/） |
| `frontend/src/pages/op/CustomerDetail.vue` | 変更 | 全件取得→find 方式を `api.getCustomer(id)` 個別取得に切替 |

## 実装詳細

### 1. LayoutOperator.vue（2行追加）

- `navItems` に `{ to: '/op/customers', icon: 'ti-users', label: '顧客管理' }` 追加（サイドバー）
- `footerItems` に `{ to: '/op/customers', icon: 'ti-users', label: '顧客' }` 追加（モバイルフッター）

### 2. api.js（1行追加）

```javascript
getCustomer: (id) => request('GET', `/customers/${id}/`),
```

既存の `getOrder(id)` と同じパターン。

### 3. CustomerDetail.vue（onMounted 簡素化）

- 変更前: `api.getCustomers()` → 全件取得 → `find(c => c.id === Number(props.id))`
- 変更後: `api.getCustomer(props.id)` → 直接取得
- 404時は `error.value` にメッセージ表示（既存エラーハンドリング踏襲）

## テスト手順（手動）

1. サイドバーに「顧客管理」リンクが表示されること（ti-users アイコン）
2. モバイルフッターに「顧客」リンクが表示されること
3. サイドバーリンク押下 → `/op/customers` に遷移すること
4. 顧客一覧から行クリック → 詳細画面で個別取得されること（ネットワークタブで `GET /api/customers/:id/` 確認）
5. 存在しないID `/op/customers/9999` → エラーメッセージ表示
6. 詳細画面の表示内容（phone/display_name/flag/memo）が正しいこと

## 次のステップ（Step2 候補）

- CustomerDetail に編集モード追加（名前・メモ・フラグ変更）
- 新規顧客作成フォーム（電話番号入力 + normalize_phone）
- api.js に `createCustomer` / `updateCustomer` 追加
