# Step4 実装報告：顧客管理 Step2（新規作成＋編集）

## 概要

運営の顧客詳細画面に「編集モード」と「新規作成モード」を追加し、顧客の作成・更新を可能にした。
バックエンド変更なし。既存の `CustomerViewSet`（POST/PATCH）をそのまま利用。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `frontend/src/api.js` | 変更 | `createCustomer` / `updateCustomer` 追加 |
| `frontend/src/pages/op/CustomerList.vue` | 変更 | [新規作成] ボタン追加 |
| `frontend/src/pages/op/CustomerDetail.vue` | 変更 | 編集モード・新規作成モード追加 |

## 実装詳細

### 1. api.js（2行追加）

```javascript
createCustomer: (body) => request('POST', '/customers/', body),
updateCustomer: (id, body) => request('PATCH', `/customers/${id}/`, body),
```

既存の `createOrder` / `updateOrder` と同じパターン。

### 2. CustomerList.vue（新規作成ボタン追加）

- 検索バー・フラグフィルタと同じ行に [新規作成] ボタンを追加
- クリックで `/op/customers/new` へ遷移
- 既存の検索・フィルタ・テーブルは変更なし

### 3. CustomerDetail.vue（編集＋新規作成モード追加）

#### モード切替

| モード | 条件 | 内容 |
|---|---|---|
| 新規作成 | `props.id === 'new'` | phone入力可。作成ボタンで POST |
| 編集 | [編集]ボタン押下 | phone表示のみ（disabled）。保存ボタンで PATCH |
| 閲覧 | デフォルト | 既存の表示レイアウト |

#### 新規作成モード
- `/op/customers/new` でアクセス（`:id` パラメータが `"new"` になる）
- フォーム項目：電話番号（必須、ハイフン入力可）、名前、フラグ、メモ
- `api.createCustomer({ store: 1, phone, display_name, flag, memo })` で POST
- `store: 1` を固定付与（単店舗前提の暫定対応）
- 電話番号の正規化はバックエンド（`validate_phone` → `normalize_phone`）に委任
- 成功時：レスポンスの `id` で `/op/customers/:id` へ `router.replace`

#### 編集モード
- [編集]ボタンで `form` に現在値をコピーして編集モードに切替
- 編集可能：`display_name`, `flag`, `memo`
- 電話番号は `disabled` 表示（変更不可）
- `api.updateCustomer(id, { display_name, flag, memo })` で PATCH（phone は送らない）
- 成功時：`customer.value` を更新し閲覧モードに復帰
- [キャンセル]：変更破棄して閲覧モードに戻る

#### エラー処理
- バリデーションエラー（phone必須・重複等）をフォーム上部にアラート表示
- DRFの field errors は既存の `request()` ヘルパーが `Object.values(data).flat().join('\n')` で連結済

## 画面フロー

```
/op/customers（一覧）
  ├ [新規作成] → /op/customers/new
  └ 行クリック → /op/customers/:id

/op/customers/new（新規作成モード）
  ↓ フォーム入力（電話番号/名前/フラグ/メモ）
  ↓ [作成]押下
  ↓ POST /api/customers/ { store:1, phone, display_name, flag, memo }
  ↓ バックエンド: validate_phone → normalize_phone
  ↓ 成功 → /op/customers/:id へ replace
  ↓ エラー → フォーム上部に表示

/op/customers/:id（閲覧モード）
  ↓ [編集]ボタン押下
  ↓ formに現在値セット → 編集モードへ

/op/customers/:id（編集モード）
  ↓ フォーム入力（名前/フラグ/メモ）※電話番号はdisabled
  ↓ [保存]押下
  ↓ PATCH /api/customers/:id/ { display_name, flag, memo }
  ↓ 成功 → customer更新 → 閲覧モードに復帰
  ↓ エラー → フォーム上部に表示
```

## store の扱い（暫定）

- `CustomerSerializer` は `fields = "__all__"` で `store` が必須フィールド
- `CustomerViewSet` に `perform_create` のオーバーライドがないため、フロントから送る必要がある
- 暫定対応として `store: 1` を固定付与（単店舗前提）
- マルチ店舗対応時は `perform_create` でリクエストユーザーから store を解決する設計に移行

## テスト手順（手動）

### 新規作成
1. `/op/customers` で [新規作成] ボタンが表示されること
2. [新規作成] → `/op/customers/new` に遷移しフォーム表示
3. 電話番号のみ入力して [作成] → 成功し詳細ページへ遷移
4. ハイフン付き電話番号（090-1234-5678）で作成 → DB に数字のみで保存
5. 電話番号なしで [作成] → HTML5 required バリデーション
6. 既存と同じ電話番号で作成 → バリデーションエラー表示（unique_together）
7. [キャンセル] → 一覧に戻ること

### 編集
8. 詳細画面で [編集] ボタンが表示されること
9. [編集] → 編集モードに切替、現在値がプリセット
10. 電話番号フィールドが disabled であること
11. 名前・メモ・フラグを変更して [保存] → 反映されること
12. フラグを「出禁」に変更 → バッジが badge-banned で表示
13. [キャンセル] → 変更が破棄され閲覧モードに戻ること

### エラー処理
14. API失敗時 → フォーム上部にエラーメッセージ表示
15. 保存中 → ボタンが「保存中...」に変わりdisabledになること

## 設計判断

- **ルート追加なし**: `/op/customers/new` は既存の `:id` ルートで `id="new"` として処理。`isNew` computed で判定
- **phone は PATCH で送らない**: キーフィールドの意図しない変更を防止
- **store: 1 固定**: バックエンド変更を避ける暫定対応。マルチ店舗化時に要修正
- **フォーム共通化**: 新規・編集で同じフォームを使用し、phone の入力可否のみ切替

## 次のステップ（Step3 候補）

- 予約履歴リンク（CustomerDetail → orders フィルタ遷移）
- store の自動付与（backend `perform_create` 追加）
- 顧客削除 / 無効化
- サーバーサイド検索・ページング対応
