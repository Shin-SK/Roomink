# 顧客CSV取込拡張 引き継ぎ報告書

## 概要

既存の顧客CSV取込を、旧システムからの移行に使える安全な顧客マスタ取込へ拡張した。
元CSVを追加取得できない前提のため、UTF-8とCP932（Shift-JIS）、英語・日本語ヘッダの双方を受理する。

利用履歴は予約・売上集計へ影響させず、顧客ごとの旧システム参照情報として原文を保存する。

## 変更ファイル

- `core/models.py`
- `core/migrations/0055_customer_email.py`
- `core/admin.py`
- `core/views.py`
- `core/urls.py`
- `core/test_customer_csv_import.py`
- `core/test_operator_api_permissions.py`
- `frontend/src/api.js`
- `frontend/src/pages/op/SettingsCsvImport.vue`
- `frontend/src/pages/op/CustomerDetail.vue`
- `frontend/src/pages/op/CustomerList.vue`
- `frontend/src/pages/op/manualData.js`

## 実装内容

- Customerへ任意のメールアドレス欄を追加
- Customerへ旧システム利用履歴の参照欄を追加
- 顧客詳細画面でメールアドレスを表示・編集
- 顧客一覧の画面内検索へメールアドレスを追加
- 顧客CSVエクスポートへメールアドレスを追加
- CSV取込画面へ種類別の雛形ダウンロードを追加
- 顧客CSVで以下の日本語項目を受理
  - 名前
  - 電話番号（必須）
  - メールアドレス
  - 利用履歴
  - 顧客メモ
  - 運営メモ
  - フラグ（なし・要注意・出禁）
  - 出禁種別（なし・店出禁・個別セラピNG）
- `備考`は安全のため運営専用メモへ取り込む
- `利用履歴`は改行を含むセルも原文のまま保存し、Roominkの予約・売上集計には含めない
- UTF-8 BOMとCP932（Shift-JIS）を自動判定
- プレビューで行別エラー・既存顧客更新警告を表示
- 電話番号を正規化し、同じCSV内の重複を拒否
- 電話番号一致時は既存顧客を更新。ただし空欄の任意項目で既存値を消さない
- CSV取込では顧客ログインアカウントを作成せず、SMSも送信しない
- 取込と雛形ダウンロードはmanager限定

## migration

- `0055_customer_email`
- Customerへ空欄可・既定値空文字のEmailFieldと旧システム利用履歴TextFieldを追加するだけで、既存行の更新処理はない

## テスト結果

- 関連テスト: 7件成功
- Django全テスト: 265件成功
- `manage.py check`: 問題なし
- `makemigrations --check --dry-run`: 追加差分なし
- Python構文検査: 成功
- Vue production build: 成功
- `git diff --check`: 成功

## 残課題

今回の利用履歴は、追加資料を取得できない条件に合わせた参照用の原文保存である。日付・キャスト・コース・金額を個別に検索・集計する構造化履歴ではない。

将来、元データの列構造が確定した場合のみ、通常予約とは分離した構造化履歴へ発展させる。既存Orderへ自動変換して売上へ混ぜる処理は行わない。

## 手動確認事項

- managerで設定 > CSVインポートを開き、顧客の雛形をダウンロードできること
- 雛形へテスト顧客を1件入力し、プレビュー後に取込できること
- 顧客詳細でメール、顧客メモ、運営メモ、出禁情報が表示されること
- 顧客詳細で旧システム利用履歴が改行を保って表示されること
- 本番反映時にrelease phaseでmigration `0055`が成功すること

## 本番影響

この時点ではローカル実装・検証のみ。本番デプロイ、本番migration、本番データ取込は実施していない。
