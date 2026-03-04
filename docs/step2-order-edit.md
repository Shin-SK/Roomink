# Step2 実装報告：予約編集（日時・担当・メモ変更）

## 概要

運営の予約詳細画面（/op/orders/:id）に「編集モード」を追加し、日時変更・担当キャスト変更・メモ編集を可能にした。
バックエンドは `OrderUpdateSerializer` を1つ追加し、既存の `ModelViewSet` の PATCH を活用。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `frontend/src/pages/op/OrderDetail.vue` | 変更 | 編集モード追加（フォーム表示/保存/キャンセル） |
| `frontend/src/api.js` | 変更 | `updateOrder(id, body)` 追加（PATCH） |
| `core/serializers.py` | 変更 | `OrderUpdateSerializer` 追加（バリデーション付き） |
| `core/views.py` | 変更 | `get_serializer_class` に update/partial_update 分岐追加 + import |

## 実装詳細

### 1. api.js（1行追加）

```javascript
updateOrder: (id, body) => request('PATCH', `/orders/${id}/`, body),
```

既存の `request()` ヘルパーを利用。CSRF トークン・credentials は既存の仕組みで自動付与。

### 2. OrderDetail.vue（編集モード追加）

- **[編集]ボタン**：アクションカードの最上部に追加。DONE/CANCELLED 状態では disabled。
- **編集モード開始** (`startEdit`)：
  - 現在の `order` の値を `editForm` にコピー（datetime-local 形式に変換）
  - キャスト一覧を `api.getCasts()` で取得（初回のみ、以降キャッシュ）
- **フォーム項目**：
  - 開始日時（`datetime-local`）
  - 終了日時（`datetime-local`）
  - 担当キャスト（`<select>` でキャスト一覧から選択）
  - メモ（`<textarea>`）
- **保存** (`saveEdit`)：`api.updateOrder()` で PATCH → 成功時 `order` を更新し閲覧モードに戻る
- **キャンセル** (`cancelEdit`)：編集モードを閉じるだけ（変更破棄）
- **エラー表示**：バリデーションエラー（シフト不在、キャスト重複等）をフォーム上部に表示
- **運営メモカード**：既存の未接続 textarea を `<p>` 表示に変更（編集はフォーム経由に統一）
- **編集中はステータス変更ボタンを disabled** にして操作衝突を防止

### 3. OrderUpdateSerializer（新規）

```python
class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["cast", "start", "end", "memo"]
```

**バリデーション（`validate` メソッド）**：
- cast / start / end のいずれかが変更された場合のみ実行（memo のみ変更時はスキップ）
- `end > start` チェック
- `ShiftAssignment` 照合 → room を自動再割当
- キャスト重複チェック（自身を exclude）
- ルーム重複チェック（自身を exclude）
- `to_representation` で `OrderSerializer` 形式のレスポンスを返す

### 4. views.py（2行変更）

```python
def get_serializer_class(self):
    if self.action == "create":
        return OrderCreateSerializer
    if self.action in ("update", "partial_update"):
        return OrderUpdateSerializer  # ← 追加
    return OrderSerializer
```

## 編集フロー

```
/op/orders/:id（閲覧モード）
  ↓ [編集]ボタン押下
  ↓ api.getCasts() でキャスト一覧取得
  ↓ editForm に現在値をセット → 編集モードへ

編集モード
  ↓ フォーム入力（日時/キャスト/メモ）
  ↓ [保存]押下
  ↓ PATCH /api/orders/:id/ (cast, start, end, memo)
  ↓
  ↓ ── バックエンド ──
  ↓ OrderUpdateSerializer.validate()
  ↓   ├ end > start?
  ↓   ├ ShiftAssignment存在? → room自動割当
  ↓   ├ キャスト重複なし?
  ↓   └ ルーム重複なし?
  ↓ 成功 → order更新 → OrderSerializer形式でレスポンス
  ↓
  ↓ フロントエンド：order.value更新 → 閲覧モードに復帰

エラー時
  ↓ バリデーションエラーをフォーム上部に表示
  ↓ 編集モード維持（ユーザーが修正可能）
```

## バリデーション詳細

| チェック項目 | 条件 | エラーメッセージ |
|---|---|---|
| 時刻逆転 | `end <= start` | 終了時刻は開始時刻より後にしてください |
| シフト不在 | 対象キャストの ShiftAssignment が該当時間帯にない | このキャストは指定日時にシフトがありません |
| キャスト重複 | 同キャスト・同時間帯にアクティブな別注文あり | このキャストは指定時間に予約が入っています |
| ルーム重複 | 同ルーム・同時間帯にアクティブな別注文あり | 指定ルームは使用中です |

※ memo のみの変更時はこれらのチェックをスキップ（不要な API 呼び出しを回避）

## テスト手順（手動）

1. `/op/orders/:id` を開き、[編集]ボタンが表示されていること
2. [編集]押下 → フォームが表示され、現在値がプリセットされていること
3. 日時を変更して[保存] → 更新が反映されること
4. キャストを変更して[保存] → room が自動的に再割当されること（ID情報カードで確認）
5. シフトのない時間帯に変更 → エラーメッセージ表示
6. 他の予約と重複する時間帯に変更 → エラーメッセージ表示
7. メモのみ変更 → バリデーションなしで即保存されること
8. [キャンセル]押下 → 編集前の値に戻ること
9. DONE / CANCELLED 状態の予約 → [編集]ボタンが disabled であること
10. 編集モード中 → 承認/キャンセル/完了ボタンが disabled であること

## 設計判断

- **編集可能フィールドを cast / start / end / memo に限定**：コース・顧客・オプション変更は運用上「キャンセル→再作成」が安全なため対象外
- **room は自動割当**：ShiftAssignment からルーム情報を取得し自動セット（手動選択不要）
- **OrderCreateSerializer のバリデーションを踏襲**：重複チェック・シフトチェックは作成時と同等のロジック（ただし `exclude(pk=self)` で自身を除外）
- **PUT も OrderUpdateSerializer を通す**：意図しないフィールド上書きを防止

## 次のステップ（Step3 候補）

- 予約一覧画面でのインライン編集
- 予約作成フォームの改善（日時ピッカー等）
- キャスト指名変更時の通知連携
