# Roomink CSS/SCSS 構造 - Bootstrap 5 ベース

## ✨ 特徴

- **Bootstrap 5完全ベース**：カード、ボタン、フォーム、テーブル等は全てBootstrapを使用
- **Roominkカラーテーマ**：Bootstrap変数を上書きしてRoominkカラーを適用
- **独自機能のみカスタム**：タイムライン、予約ブロック、スケジュール機能

## ディレクトリ構成

```
assets/css/
├── styles.scss              # メインエントリーポイント
├── _timeline.scss           # タイムライン（Fresha風）
├── global/
│   ├── _mixins.scss        # Mixins
│   └── _reset.scss         # リセットCSS
└── components/
    ├── _theme.scss         # Bootstrapテーマ変数上書き ⭐️
    ├── _variables.scss     # 追加CSS変数（ステータスバッジ）
    ├── _layout.scss        # レイアウト（サイドバー、ヘッダー）
    ├── _booking.scss       # 予約ブロック
    ├── _schedule.scss      # 新スケジュール
    └── _timeline-legacy.scss # 旧タイムライン（互換性維持）
```

## HTMLでの使用方法

### Bootstrap標準コンポーネントを使う

```html
<!-- カード -->
<div class="card">
  <div class="card-header">タイトル</div>
  <div class="card-body">内容</div>
</div>

<!-- ボタン -->
<button class="btn btn-primary">送信</button>
<button class="btn btn-success">承認</button>
<button class="btn btn-outline-secondary">キャンセル</button>

<!-- フォーム -->
<div class="mb-3">
  <label class="form-label">名前</label>
  <input type="text" class="form-control">
</div>

<!-- テーブル -->
<table class="table table-hover">
  <thead>
    <tr><th>名前</th><th>予約日時</th></tr>
  </thead>
  <tbody>
    <tr><td>山田太郎</td><td>2026-02-15 14:00</td></tr>
  </tbody>
</table>

<!-- アラート -->
<div class="alert alert-success">予約が完了しました</div>
<div class="alert alert-warning">確認が必要です</div>

<!-- バッジ -->
<span class="badge bg-primary">新規</span>
<span class="badge bg-success">承認済</span>

<!-- レイアウトユーティリティ -->
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2>タイトル</h2>
  <button class="btn btn-sm btn-primary">追加</button>
</div>
```

### Roomink独自バッジ

```html
<span class="badge badge-pending">申請中</span>
<span class="badge badge-approved">承認済</span>
<span class="badge badge-unconfirmed">未確認</span>
<span class="badge badge-attention">要注意</span>
<span class="badge badge-banned">BAN</span>
```

## コンパイル方法

```bash
# 開発時（watch モード）
sass --watch assets/css/styles.scss:assets/css/styles.css

# 本番ビルド（圧縮）
sass --style compressed assets/css/styles.scss:assets/css/styles.css

# 1回だけコンパイル
sass assets/css/styles.scss:assets/css/styles.css
```

## 各ファイルの役割

### `_theme.scss` ⭐️ 重要
- Bootstrap変数を上書き
- Roominkカラーパレット定義
- `$primary`, `$success`, `$danger`等を設定

### `_variables.scss`
- Bootstrapに無い独自CSS変数
- ステータスバッジ用の色定義

### `_layout.scss`
- `.app-wrapper`、`.sidebar`、`.main-content`
- `.customer-layout`（顧客向けレイアウト）
- レスポンシブ対応

### `_booking.scss`
- 予約ブロック
- `.booking-block-*`、`.cast-icon-*`

### `_schedule.scss`
- 新スケジュール（Fresha風）
- `.rk-schedule`、`.rk-timeline`、`.rk-block`

### `_timeline.scss` / `_timeline-legacy.scss`
- タイムライン機能（旧・新）

## 🎨 Roominkカラー

Bootstrap変数で定義されているため、全てのBootstrapコンポーネントに自動適用されます：

- **Primary**: `#2A9D8F` (ティールグリーン)
- **Success**: `#10B981`
- **Warning**: `#F59E0B`
- **Danger**: `#EF4444`
- **Info**: `#3B82F6`

## 📝 Bootstrap 5 クラス一覧（主要なもの）

### レイアウト
- `.container`, `.container-fluid`
- `.row`, `.col-*`
- `.d-flex`, `.d-grid`
- `.justify-content-*`, `.align-items-*`
- `.gap-*`, `.g-*`

### スペーシング
- `.m-*`, `.mt-*`, `.mb-*`, `.mx-*`, `.my-*` (margin)
- `.p-*`, `.pt-*`, `.pb-*`, `.px-*`, `.py-*` (padding)
- 0〜5のスケール

### テキスト
- `.text-*` (center, start, end, muted, primary等)
- `.fw-*` (bold, normal, light)
- `.fs-*` (1〜6)

### カラー
- `.bg-*` (primary, success, warning, danger, light, dark)
- `.text-*` (primary, success, warning, danger, muted)
- `.border-*`

## 削除されたファイル

Bootstrap標準機能を使うため、以下は削除されました：

- ❌ `components/_badge.scss` → Bootstrap `.badge`を使用
- ❌ `components/_button.scss` → Bootstrap `.btn`を使用
- ❌ `components/_card.scss` → Bootstrap `.card`を使用
- ❌ `components/_form.scss` → Bootstrap `.form-*`を使用
- ❌ `components/_table.scss` → Bootstrap `.table`を使用
- ❌ `components/_list.scss` → Bootstrap `.list-group`を使用
- ❌ `components/_alert.scss` → Bootstrap `.alert`を使用
- ❌ `components/_base.scss` → Bootstrap Rebootを使用
- ❌ `_custom.scss` → 不要

## 📚 参考リンク

- [Bootstrap 5 Documentation](https://getbootstrap.com/docs/5.3/getting-started/introduction/)
- [Bootstrap 5 Components](https://getbootstrap.com/docs/5.3/components/alerts/)
- [Bootstrap 5 Utilities](https://getbootstrap.com/docs/5.3/utilities/api/)
- [Sass Documentation](https://sass-lang.com/documentation/)

## 注意事項

- HTMLではBootstrapのクラスを最優先で使用してください
- カスタムクラスは最小限に（レイアウト、タイムライン、予約ブロックのみ）
- 新しいコンポーネントが必要な場合は、まずBootstrapに存在しないか確認してください
