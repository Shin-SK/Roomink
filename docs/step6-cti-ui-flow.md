# Step6 実装報告：CTI運営フローをUIで完結

## 概要

Dashboard の未対応コールから、運営が `start → phone → 顧客作成/予約作成` の一連処理をUI上で完結できるようにした。
バックエンド変更なし。既存の CTI API（start/done/notes）をフロントから活用。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `frontend/src/pages/op/Dashboard.vue` | 変更 | 対応ボタンで start API → phone遷移、完了ボタン追加 |
| `frontend/src/pages/op/Phone.vue` | 変更 | 顧客未存在時「この番号で顧客作成」ボタン追加 |
| `frontend/src/pages/op/CustomerDetail.vue` | 変更 | 新規作成モードで query.phone を初期値にセット |

## 実装詳細

### 1. Dashboard.vue（CTIフロー強化）

#### 対応ボタン（NEW → start → phone遷移）
- 「対応」ボタン押下で `api.ctiCallStart(call.id)` を実行
- 成功後 `/op/phone?phone=<from_phone>` へ遷移
- 失敗時（他の運営が先に開始済み等）はエラー表示 + キュー再取得
- 二重クリック防止：call ごとに loading 状態を管理

#### 完了ボタン（IN_PROGRESS → done）
- IN_PROGRESS のコールに「完了」ボタンを表示
- `api.ctiCallDone(call.id)` でステータスを DONE に変更
- 成功後キューを再取得（一覧から消える）

#### 担当者表示
- IN_PROGRESS のコールに `assigned_to`（担当者名）を表示

#### エラーハンドリング
- CTI操作の失敗をカード内にアラート表示
- キュー取得失敗は従来通り non-fatal（サイレント）

### 2. Phone.vue（顧客未存在時の誘導）

- `?phone=` で顧客が見つからない場合の警告メッセージを強化
- 「この番号で顧客作成」ボタンを追加
- ボタン押下で `/op/customers/new?phone=<phone>` へ遷移
- 顧客作成後は `/op/customers/:id` へ遷移し、改めて Phone に戻って予約作成

### 3. CustomerDetail.vue（phone 初期値セット）

- `useRoute` を追加し、`route.query.phone` を取得
- 新規作成モード（`isNew`）で `query.phone` がある場合、`form.phone` に初期セット
- 既にユーザーが入力している場合は上書きしない（onMounted 時のみ）

## 画面フロー

```
/op/dashboard
  └ 未対応コール [対応]ボタン
    ↓ POST /api/op/cti/calls/:id/start/（IN_PROGRESS + assigned_to 設定）
    ↓ 成功 → /op/phone?phone=09012345678

/op/phone?phone=09012345678
  ├ 顧客あり → 自動選択 → STEP2（予約内容入力）→ 予約作成
  └ 顧客なし → 警告表示
    └ [この番号で顧客作成] → /op/customers/new?phone=09012345678

/op/customers/new?phone=09012345678
  ↓ phone が初期値としてセット済み
  ↓ フォーム入力 → [作成]
  ↓ POST /api/customers/（store 自動付与 by Step5）
  ↓ 成功 → /op/customers/:id

/op/dashboard
  └ IN_PROGRESS コール [完了]ボタン
    ↓ POST /api/op/cti/calls/:id/done/
    ↓ キューから消える
```

## API利用（既存・バックエンド変更なし）

| エンドポイント | メソッド | 用途 |
|---|---|---|
| `/api/op/cti/queue/` | GET | 未対応コール一覧取得（2秒ポーリング） |
| `/api/op/cti/calls/:id/start/` | POST | 対応開始（NEW → IN_PROGRESS） |
| `/api/op/cti/calls/:id/done/` | POST | 対応完了（→ DONE） |

## 設計判断

- **start を先に叩く**: 遷移前に start を叩くことで、他の運営との取り合いを防止
- **失敗時は遷移しない**: start が失敗（409等）したら phone には遷移せず、キューを再取得
- **notes UI は見送り**: 主導線（start → phone → 予約作成）を優先。notes は後続Stepで対応
- **phone 初期値**: query param 経由で渡すことで、Phone → CustomerDetail 間のデータ連携をシンプルに保つ

## テスト手順（手動）

### CTI対応フロー
1. Dashboard に未対応コール（NEW）が表示されること
2. [対応]ボタン押下 → spinner 表示 → `/op/phone?phone=xxx` へ遷移
3. Dashboard に戻ると当該コールが IN_PROGRESS になっていること
4. IN_PROGRESS コールに [完了] ボタンが表示されること
5. [完了] 押下 → コールがキューから消えること

### 顧客未存在フロー
6. `/op/phone?phone=未登録番号` → 「顧客が見つかりません」+ 「この番号で顧客作成」ボタン表示
7. [この番号で顧客作成] → `/op/customers/new?phone=xxx` へ遷移
8. phone フィールドに番号が初期入力されていること
9. そのまま [作成] → 顧客作成成功

### エラーハンドリング
10. 同じコールを2つのブラウザで同時に [対応] → 片方が失敗しエラー表示
11. [対応] 失敗後、キューが再取得されること

## 次のステップ候補

- notes UI（対応中コールにメモを追加）
- CTI対応履歴表示（DONE一覧）
- Phone画面から顧客作成後、自動で Phone に戻って予約作成を継続
- 顧客検索のサーバーサイド化（大量顧客対応）
