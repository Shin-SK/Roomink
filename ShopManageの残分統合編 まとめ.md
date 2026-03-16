# ShopManageの残分統合編 まとめ

## まず結論

ShopManage の設定項目をそのまま横移植するのではなく、
Roomink では **意味ごとに再編成して統合** する方針で進める。

理由は明確で、ShopManage 側は歴史的に増えた項目が横並びしており、

- 予約に関わる設定
- 料金に関わる設定
- 通知に関わる設定
- 会計・給与に関わる設定

が混在しているため。
Roomink ではこの混在を最初から整理して、後の売上・給与・分析計算につなげる。

---

## Roominkでの設定再編方針

| # | 分類 |
|---|------|
| 1 | 予約設定 |
| 2 | 料金設定 |
| 3 | 運営設定 |
| 4 | 通知設定 |
| 5 | 会計・給与設定 |

---

## 1. 予約設定

予約成立やスケジュール運用に直接関わる設定。

### 既にあるもの

- キャスト管理
- ルーム管理
- コース管理
- オプション管理

### これから追加するもの

- 延長管理
- 指名料管理
- 休憩・その他管理
- 営業時間設定
- オンライン予約設定

### 各項目の意味

| 項目 | 説明 |
|------|------|
| 延長管理 | 予約途中・会計時に追加される時間単位。コースとは別マスタにする。 |
| 指名料管理 | 指名種別ごとの追加料金。最初は単純料金で開始し、歩合列は後で拡張。 |
| 休憩・その他管理 | 休憩・講習・移動などの時間ブロック管理。予約にも給与にも影響しうる。 |
| 営業時間設定 | 店舗として予約受付可能な時間帯。 |
| オンライン予約設定 | 顧客向け予約画面の公開条件や受付制御。 |

---

## 2. 料金設定

予約価格や会計計算に関わる設定。

### 追加候補

| 項目 | 説明 |
|------|------|
| 割引管理 | 固定額 or 率での割引ルール。 |
| 手数料管理 | カード手数料など、決済に伴う加算/控除。 |
| 加算料金管理 | 交通費などを含む追加料金ルール。交通費単独ではなく汎用加算に吸収する方針。 |

---

## 3. 運営設定

店舗運営・導線分析・現場共有に関わる設定。

### 追加候補

| 項目 | 説明 |
|------|------|
| 媒体管理 | どこから予約が来たかを持つ流入元マスタ。 |
| ノート設定 | 店全体や予約単位で共有する掲示・メモの運用設定。 |
| 利用表示/掲示設定 | 予約画面や管理画面上で何を見せるかの制御。 |

---

## 4. 通知設定

SMS / LINE / メールなどの通知に関する設定。

### 重要方針

ここは一番壊れやすいので、**独立ドメインとして扱う**。
「LINE送信設定」という1画面に押し込まない。

### 3層で分ける

| 層 | 説明 |
|----|------|
| チャネル設定 | LINE / SMS / Email の接続情報 |
| 通知ルール | どのイベントで、誰に、どのチャネルで送るか |
| 通知テンプレート | 実際の文面 |

### 優先順位

通知は重要だが設計を雑にすると崩れるので、後半で着手する。

---

## 5. 会計・給与設定

売上・給与・精算・分析の土台になる設定。

### ShopManage側の散らばった項目

- 経費
- 調整金
- スカウト
- 雑費
- 指名料歩合
- 休憩その他の給与反映

### Roomink側の方針

バラバラに持たず、**共通マスタとして統合** する。

### 統合方針

経費・調整金・スカウト・雑費は別画面4つにせず、
まずは **精算項目/会計項目マスタ** にまとめる。

### 理由

後の売上計算・給与計算・PL計算で、共通構造の方が圧倒的に扱いやすい。

---

## 売上・給与計算に関する設計方針

### 結論

売上計算や給与計算は、外部APIに丸投げしない。
Roomink 内に **自前の計算コア** を持つ。

### 外部APIに任せてよい領域

- 税
- 決済
- 通知
- 会計連携

### 自前で持つべき領域

- 売上明細生成
- 給与明細生成
- 歩合計算
- 控除計算
- 調整項目反映
- 店舗粗利計算

### 要するに

「万能売上計算API」は探さない。
代わりに、設定マスタを入力として回る **売上・給与計算エンジン** を Roomink 内に設計する。

---

## 実装優先順位

### 最優先

1. 延長管理
2. 指名料管理
3. 割引管理
4. 媒体管理

### 次点

5. 休憩・その他管理
6. ノート設定
7. 手数料管理

### 後回し

8. 通知設定（LINE/SMS/テンプレ）
9. 加算料金/交通費
10. 求人媒体
11. 会計・給与項目の詳細分化

---

## この章の設計結論

- ShopManageの項目名は参考にする
- ただし構造はそのまま真似しない
- Roominkでは「予約」「料金」「運営」「通知」「会計給与」に再編成する
- 経費/調整金/スカウト/雑費は共通マスタに統合する
- 通知は独立ドメインとして扱う
- 売上・給与計算は外部API依存ではなく自前の計算コア前提で進める
- 次の着手は「延長」「指名料」「割引」「媒体」




---

# 段取りまとめ

## Step 9.5: Order 金額スナップショット導入

目的
- 過去注文の金額が、マスタ価格変更で変わらないようにする
- 延長・指名料・割引を入れる前の土台を作る

やること
- Order に以下を追加
  - course_name
  - course_price
  - options_price
  - total_price
- data migration で既存注文に snapshot を埋める
- 新規注文作成時に snapshot を自動保存
- 既存の金額参照箇所を snapshot 参照に切替

対象ファイル
- core/models.py
- core/migrations/xxxx_order_price_snapshot.py
- core/serializers.py
- core/views.py
- docs/step9.5-order-price-snapshot-report.md

受け入れ条件
- 新規注文で snapshot が保存される
- 既存注文に snapshot が埋まる
- Course.price を変えても過去注文 total_price が変わらない
- KPI / マイページ / CastToday が壊れない

このStepではやらない
- extension_price
- nomination_fee
- discount_amount
- フロント変更

## Step 10: 延長管理

目的
- 予約後・会計時に加算できる延長マスタを追加する
- コースと切り分けて管理する

やること
- Extension モデル追加
  - store
  - name
  - duration
  - price
  - sort_order
  - is_active
- Extension の CRUD API
- 設定配下に延長管理画面を追加
- Settings に「延長」メニュー追加

対象ファイル
- core/models.py
- core/serializers.py
- core/views.py
- core/urls.py
- frontend/src/api.js
- frontend/src/pages/op/SettingsExtensions.vue
- frontend/src/router.js
- frontend/src/pages/op/Settings.vue
- docs/step10-extension-report.md

受け入れ条件
- 延長の一覧・追加・編集・削除ができる
- duration / price を持てる
- 設定トップから遷移できる
- 既存の設定画面パターンを壊さない

このStepではやらない
- Order に extension を適用する処理
- 延長料金の会計反映

## Step 11: 指名料管理

目的
- 指名種別ごとの追加料金マスタを持てるようにする

やること
- NominationFee モデル追加
  - store
  - name
  - price
  - sort_order
  - is_active
- CRUD API 追加
- 設定配下に指名料管理画面を追加
- Settings に「指名料」メニュー追加

対象ファイル
- core/models.py
- core/serializers.py
- core/views.py
- core/urls.py
- frontend/src/api.js
- frontend/src/pages/op/SettingsNominationFees.vue
- frontend/src/router.js
- frontend/src/pages/op/Settings.vue
- docs/step11-nomination-fee-report.md

受け入れ条件
- 指名料の一覧・追加・編集・削除ができる
- 設定トップから遷移できる
- 既存の設定UIパターンに揃っている

このStepではやらない
- 歩合率列
- キャスト別歩合テーブル
- Order への適用

## Step 12: 割引管理

目的
- 固定額/定率の割引マスタを持てるようにする

やること
- Discount モデル追加
  - store
  - name
  - discount_type (fixed / percent)
  - value
  - sort_order
  - is_active
- CRUD API 追加
- 設定配下に割引管理画面を追加
- Settings に「割引」メニュー追加

対象ファイル
- core/models.py
- core/serializers.py
- core/views.py
- core/urls.py
- frontend/src/api.js
- frontend/src/pages/op/SettingsDiscounts.vue
- frontend/src/router.js
- frontend/src/pages/op/Settings.vue
- docs/step12-discount-report.md

受け入れ条件
- 割引の一覧・追加・編集・削除ができる
- fixed / percent を持てる
- 設定トップから遷移できる

このStepではやらない
- Order への割引適用ロジック
- 複数割引の優先順位処理

## Step 13: 媒体管理

目的
- 予約流入元を管理できるようにする
- 売上分析・集客分析の起点を作る

やること
- Medium または LeadSource モデル追加
  - store
  - name
  - category（必要なら）
  - sort_order
  - is_active
- CRUD API 追加
- 設定配下に媒体管理画面を追加
- Settings に「媒体」メニュー追加

対象ファイル
- core/models.py
- core/serializers.py
- core/views.py
- core/urls.py
- frontend/src/api.js
- frontend/src/pages/op/SettingsMediums.vue
- frontend/src/router.js
- frontend/src/pages/op/Settings.vue
- docs/step13-medium-report.md

受け入れ条件
- 媒体の一覧・追加・編集・削除ができる
- 設定トップから遷移できる
- 将来 Order / Customer に紐づけられる形になっている

このStepではやらない
- Order / Customer への FK 追加
- 分析画面

## Step 14: Order への延長・指名料・割引の接続設計

目的
- 追加したマスタを、実際の注文金額に反映できるようにする
- total_price 再計算の責務を整理する

やること
- Order に何を持つか確定
  - extension_price
  - nomination_fee
  - discount_amount
  など
- 適用単位を決める
  - Order に直接持つか
  - 中間テーブルを作るか
- total_price 再計算タイミングを整理
  - 作成時
  - 更新時
  - 延長追加時
  - 割引適用時
- 実装前の設計レビュー

対象ファイル
- まずは docs ベース
- docs/step14-order-pricing-connection-review.md

受け入れ条件
- 延長・指名料・割引をどう Order に乗せるかが文章で確定している
- total_price の再計算責務が明確になっている

このStepではやらない
- 本実装

## Step 15: Order 金額計算エンジン MVP

目的
- Order の売上計算を、都度ベタ書きではなく一箇所で計算できるようにする

やること
- pricing / calculator 系のサービス層を導入
- MVP として以下を計算対象にする
  - course_price
  - options_price
  - extension_price
  - nomination_fee
  - discount_amount
  - total_price
- 既存の参照箇所をこの計算結果前提に寄せる

対象ファイル
- core/services/pricing.py など
- core/serializers.py
- core/views.py
- docs/step15-pricing-engine-mvp-report.md

受け入れ条件
- total_price の更新責務が一箇所に寄る
- 参照箇所ごとの計算散乱が減る

このStepではやらない
- 給与計算
- PL計算

## Step 16: 休憩・その他管理

目的
- 休憩、講習、移動などの時間ブロックを管理し、将来の給与計算に繋げる

やること
- TimeBlockType モデル追加
  - store
  - name
  - category
  - duration
  - affects_payroll
  - affects_schedule
  - sort_order
  - is_active
- CRUD API
- 設定配下の管理画面追加

対象ファイル
- core/models.py
- core/serializers.py
- core/views.py
- core/urls.py
- frontend/src/api.js
- frontend/src/pages/op/SettingsTimeBlockTypes.vue
- frontend/src/router.js
- frontend/src/pages/op/Settings.vue
- docs/step16-time-block-type-report.md

受け入れ条件
- 休憩・その他項目を一覧・追加・編集・削除できる
- 将来の給与計算・スケジュール制御に使える構造になっている

## Step 17: 手数料・加算料金管理

目的
- カード手数料や交通費などの加算/控除ルールを整理する

やること
- PaymentFeeRule または SurchargeRule を追加
- CRUD API
- 設定配下の管理画面追加

対象ファイル
- core/models.py
- core/serializers.py
- core/views.py
- core/urls.py
- frontend/src/api.js
- frontend/src/pages/op/SettingsSurcharges.vue
- frontend/src/router.js
- frontend/src/pages/op/Settings.vue
- docs/step17-surcharge-report.md

受け入れ条件
- 汎用加算料金ルールを管理できる
- 交通費を独立項目にせず吸収できる

## Step 18: ノート設定・媒体の実運用接続

目的
- 運営設定を単なるマスタではなく、現場運用に使える形にする

やること
- ノート本文モデル or 掲示板モデルの設計
- 媒体を Order / Customer に紐づける設計
- 必要なら表示設定も追加

対象ファイル
- docs/step18-operation-settings-review.md
- その後に実装分割

受け入れ条件
- ノートと媒体の「設定」と「実データ」の境界が整理されている

## Step 19: 通知設定ドメイン設計

目的
- LINE / SMS / テンプレ / 通知ルールを独立設計する

やること
- NotificationChannel
- NotificationRule
- NotificationTemplate
- StoreNotificationConfig
の責務分割をレビューする
- 既存 SmsLog との整合を決める

対象ファイル
- docs/step19-notification-domain-review.md

受け入れ条件
- SmsLog は配信ログとして残すかが決まる
- 通知設定のモデル分割が確定する

このStepではやらない
- 実送信の本実装

## Step 20: 会計・給与設定の共通マスタ設計

目的
- 経費 / 調整金 / スカウト / 雑費 を共通構造で扱えるようにする

やること
- AdjustmentCategory などの共通マスタ設計
- category / affects / default_sign などの整理
- 将来の歩合補助設定とどこで分けるか決める

対象ファイル
- docs/step20-adjustment-master-review.md

受け入れ条件
- どこまで共通マスタで持ち、どこから別テーブルに分けるかが確定している

## Step 21: 売上計算エンジン設計

目的
- 設定マスタ群を入力にして、売上・給与・粗利に展開できる計算コアの骨格を決める

やること
- Order 明細の構造整理
- line item の分類
- subtotal / total / payroll_basis の考え方整理
- どの時点で snapshot を固定するか整理

対象ファイル
- docs/step21-sales-engine-review.md

受け入れ条件
- 売上計算エンジンの責務が文書で固まる
- 外部APIに任せる領域と自前領域が明確

## Step 22: E2E 再確認

目的
- ここまで追加した設定と計算が、予約導線を壊していないか確認する

やること
- 顧客予約
- オペ確認
- 電話予約
- キャストACK
- Schedule
- マイページ
- KPI
- 設定値反映
を通しで確認する

対象ファイル
- docs/step22-e2e-regression-report.md

受け入れ条件
- 設定追加後も予約導線が壊れていない
- 金額表示が snapshot ベースで安定している
