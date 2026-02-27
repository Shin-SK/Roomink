# Roomink HTML Partials（パーツ化）

全HTMLファイルを共通パーツで管理する仕組みを導入しました。

## 📁 ファイル構成

```
assets/
├── partials/                    # 共通HTMLパーツ
│   ├── head-operator.html       # 運営側 <head>
│   ├── head-customer.html       # 顧客・キャスト側 <head>
│   ├── sidebar-operator.html    # 運営側サイドバー
│   ├── header-customer.html     # 顧客側ヘッダー
│   ├── header-cast.html         # キャスト側ヘッダー
│   └── scripts.html             # 共通スクリプト
└── js/
    └── include.js               # パーシャルローダー
```

## 🚀 使い方

### 運営側ページ（op_*.html）

```html
<!DOCTYPE html>
<html lang="ja">
<head data-include="assets/partials/head-operator.html">
  <title>Dashboard - Roomink</title>
</head>
<body data-page="dashboard">
  <div class="app-wrapper">
    <aside data-include="assets/partials/sidebar-operator.html"></aside>
    
    <div class="main-content">
      <!-- ページ固有のコンテンツ -->
    </div>
  </div>
  
  <script src="assets/js/include.js"></script>
  <div data-include="assets/partials/scripts.html"></div>
</body>
</html>
```

### 顧客側ページ（cu_*.html）

```html
<!DOCTYPE html>
<html lang="ja">
<head data-include="assets/partials/head-customer.html">
  <title>マイページ - Roomink</title>
</head>
<body data-page="mypage">
  <div class="customer-layout">
    <header data-include="assets/partials/header-customer.html"></header>
    
    <div class="customer-content">
      <!-- ページ固有のコンテンツ -->
    </div>
  </div>
  
  <script src="assets/js/include.js"></script>
  <div data-include="assets/partials/scripts.html"></div>
</body>
</html>
```

### キャスト側ページ（ca_*.html）

```html
<!DOCTYPE html>
<html lang="ja">
<head data-include="assets/partials/head-customer.html">
  <title>本日の予約 - Roomink Cast</title>
</head>
<body data-page="today">
  <div class="customer-layout">
    <header data-include="assets/partials/header-cast.html"></header>
    
    <div class="customer-content">
      <!-- ページ固有のコンテンツ -->
    </div>
  </div>
  
  <script src="assets/js/include.js"></script>
  <div data-include="assets/partials/scripts.html"></div>
</body>
</html>
```

## ⚙️ 仕組み

1. **`data-include`属性**：読み込むHTMLファイルのパスを指定
2. **`include.js`**：ページ読み込み時に全パーシャルを取得して展開
3. **`data-page`属性**：現在ページを識別し、ナビのアクティブ状態を自動設定

### ナビゲーションのアクティブ制御

`include.js`が自動で以下を行います：
- `<body data-page="dashboard">`を読み取り
- `sidebar-operator.html`内の`<a data-page="dashboard">`に`.active`クラスを付与

## 🔧 パーツ編集時の注意点

### サイドバー・ヘッダーの編集

各リンクに`data-page`属性を追加：

```html
<!-- sidebar-operator.html -->
<li><a href="op_dashboard.html" class="nav-link" data-page="dashboard">
  <i class="ti ti-layout-dashboard"></i> Dashboard
</a></li>
```

### 新しいページを追加する場合

1. HTMLファイルに`data-page="new-page"`を追加
2. 対応するパーシャルに`data-page="new-page"`のリンクを追加

## ⚠️ 重要な制限

### ローカルサーバーが必須

`file://`プロトコルでは`fetch()`が制限されるため、ローカルサーバーが必要：

```bash
# Python 3
cd /path/to/html
python3 -m http.server 8000

# Node.js
npx http-server -p 8000

# PHP
php -S localhost:8000
```

その後、`http://localhost:8000`でアクセス。

## ✅ パーツ化済みファイル一覧

### 運営側（7ファイル）
- [x] op_dashboard.html
- [x] op_schedule.html
- [x] op_inbox.html
- [x] op_order.html
- [x] op_customers.html
- [x] op_phone.html
- [x] op_shift.html

### 顧客側（4ファイル）
- [x] cu_mypage.html
- [x] cu_booking.html
- [x] cu_reservation.html
- [x] cu_submitted.html

### キャスト側（1ファイル）
- [x] ca_mypage.html

### その他（1ファイル）
- [x] index.html

## 🎯 メリット

1. **一元管理**：ヘッダー・ナビを1箇所で編集すれば全ページに反映
2. **メンテナンス性向上**：リンク追加/削除が簡単
3. **コード量削減**：各HTMLファイルがシンプルに
4. **アクティブ状態自動化**：`data-page`で自動制御

## 📝 今後の拡張

将来的にReact/Vue/Next.jsに移行する場合も、この構造をそのまま活かせます：
- パーシャル → コンポーネント化
- `data-include` → `import`文
- `include.js` → フレームワークのルーター
