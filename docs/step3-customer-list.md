# Step3 実装報告：顧客管理 Step1A（閲覧：一覧＋詳細）

## 概要

運営（/op）で顧客一覧と顧客詳細を閲覧できるようにした。
このStepでは「新規作成」「編集」「削除」は未実装。ナビゲーションリンク追加も次Step（1B）に回した。
バックエンド変更なし。既存の `GET /api/customers/` をそのまま利用。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `frontend/src/router.js` | 変更 | `/op/customers` と `/op/customers/:id` ルート追加 |
| `frontend/src/pages/op/CustomerList.vue` | 新規 | 顧客一覧画面（検索・フラグ絞り込み） |
| `frontend/src/pages/op/CustomerDetail.vue` | 新規 | 顧客詳細画面（閲覧のみ） |

## 実装詳細

### 1. router.js（2ルート追加）

```javascript
{ path: '/op/customers', name: 'customer-list', component: CustomerList },
{ path: '/op/customers/:id', name: 'customer-detail', component: CustomerDetail, props: true },
```

- 既存の `/op/*` ログインガード（`beforeEach`）がそのまま適用される
- `CustomerDetail` は `props: true` で `:id` をコンポーネントに渡す

### 2. CustomerList.vue（新規）

- **データ取得**: `onMounted` で `api.getCustomers()` を呼び全件取得
- **検索**: テキスト入力で `phone` / `display_name` の部分一致（クライアント側フィルタ）
- **フラグ絞り込み**: セレクトボックスで ALL / ATTENTION / BAN / NONE を切替
- **一覧テーブル**: 名前・電話番号・フラグ（バッジ表示）の3列
- **遷移**: 行クリックで `/op/customers/:id` へ `router.push`
- **エラー**: API失敗時にアラート表示
- **レスポンス形式**: `Array.isArray(data) ? data : data.results || []`（ページング有無の両方に対応）

### 3. CustomerDetail.vue（新規）

- **データ取得**: `api.getCustomers()` で全件取得し `find(c => c.id === Number(props.id))` で該当顧客を取得
  - `api.getCustomer(id)` が api.js に未定義のため、全件取得→ID検索方式を採用（api.js 変更なし制約）
- **表示項目**: 電話番号、名前、フラグ（バッジ）、メモ
- **レイアウト**: OrderDetail.vue と同じ2カラム構成（左: 情報カード、右: アクション + ID情報）
- **アクション**: 「顧客一覧に戻る」ボタンのみ（編集は次Step）
- **ID情報カード**: Customer ID, Store ID を表示

## フラグ表示

| フラグ値 | 表示テキスト | バッジクラス |
|---|---|---|
| `NONE` | なし | （バッジなし / テキスト表示） |
| `ATTENTION` | 要注意 | `badge-pending` |
| `BAN` | 出禁 | `badge-banned` |

## 画面フロー

```
URL直打ち /op/customers
  ↓ ログインガード通過
  ↓ api.getCustomers() で全件取得
  ↓
顧客一覧
  ├ 検索入力 → クライアント側フィルタ（即時反映）
  ├ フラグ絞り込み → クライアント側フィルタ
  └ 行クリック → /op/customers/:id

顧客詳細
  ├ 電話番号・名前・フラグ・メモを表示
  └ [顧客一覧に戻る] → /op/customers
```

## テスト手順（手動）

1. `/op/customers` にアクセス → 顧客一覧が表示されること
2. 検索バーに電話番号の一部を入力 → リアルタイムにフィルタされること
3. 検索バーに名前の一部を入力 → フィルタされること
4. フラグ絞り込みで「出禁」選択 → BAN 顧客のみ表示
5. フラグ絞り込みで「すべて」に戻す → 全件表示
6. 行クリック → `/op/customers/:id` に遷移し詳細表示
7. 詳細画面で電話番号・名前・フラグ・メモが正しく表示されること
8. フラグバッジ（要注意 / 出禁）が正しいスタイルで表示されること
9. [顧客一覧に戻る] → 一覧ページに戻ること
10. 未ログイン状態で `/op/customers` → `/op/login` にリダイレクトされること
11. 存在しないIDで `/op/customers/9999` → 「顧客が見つかりません」エラー表示

## 設計判断

- **api.js 変更なし**: `getCustomers()` をそのまま利用。個別取得 `getCustomer(id)` は次Stepで追加予定
- **クライアント側フィルタ**: 顧客数が少ない前提（数百件程度）。大規模化時はサーバーサイド検索（`?search=`）に移行
- **ナビゲーション未追加**: LayoutOperator の navItems 追加は次Step（1B）に回し、ファイル数制約（最大3）を遵守
- **新規CSS なし**: 既存の card / table / badge クラスのみ使用

## 次のステップ（Step1B / Step2 候補）

- LayoutOperator に顧客リンク追加（navItems / footerItems）
- api.js に `getCustomer(id)` / `createCustomer` / `updateCustomer` 追加
- CustomerDetail に編集モード追加（名前・メモ・フラグ変更）
- 新規顧客作成フォーム（電話番号入力 + normalize_phone バリデーション）
- 予約履歴リンク（`/op/schedule?customer=:id` 等）
