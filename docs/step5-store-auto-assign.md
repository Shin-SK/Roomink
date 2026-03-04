# Step5 実装報告：Customer作成のstore自動付与 + フロント store:1 撤去

## 概要

顧客新規作成時にフロントから `store` を送らなくても作成できるようにし、`store: 1` 固定を撤去。
AWS/App Runner 移行前に「store固定」という事故要因を除去。

## 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `core/serializers.py` | 変更 | `CustomerSerializer` に `read_only_fields = ["store"]` 追加 |
| `core/views.py` | 変更 | `CustomerViewSet.perform_create()` 追加 |
| `frontend/src/pages/op/CustomerDetail.vue` | 変更 | POST payload から `store: 1` を削除 |

## 実装詳細

### 1. core/serializers.py

```python
class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ["store"]  # 追加
```

- `store` を read_only にすることで、フロントから送らなくてもバリデーションを通過する
- GET レスポンスには `store` が含まれる（read_only なので返却はされる）

### 2. core/views.py（CustomerViewSet）

```python
def perform_create(self, serializer):
    store = Store.objects.order_by("id").first()
    if store is None:
        raise ValidationError({"store": "店舗が登録されていません"})
    serializer.save(store=store)
```

- 単店舗前提で `Store.objects.order_by('id').first()` を使用
- Store 未登録時は 400 エラーで明確なメッセージを返す
- マルチ店舗化時は `request.user` から store を解決する形に差し替え可能

### 3. CustomerDetail.vue

- POST payload から `store: 1` を削除
- `phone`, `display_name`, `flag`, `memo` のみ送信

## 設計判断

- **方式B採用**: `Store.objects.order_by('id').first()` による暫定自動付与
  - ユーザーモデルに store 紐付けがまだ無いため、方式A（user.store）は不可
- **read_only_fields**: シリアライザレベルで store を受け付けないようにし、意図しない store 指定を防止
- **後方互換**: フロントから store を送っても無視されるだけで壊れない
