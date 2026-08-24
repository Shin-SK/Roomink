# GPT向け引き継ぎ報告：ノート記事の並び替え

## 概要

運営画面のノート一覧から、記事を上下へ1件ずつ並び替えられるようにした。保存した順番はキャスト側のノート表示にも反映される。

## 変更ファイル

- `core/models.py`
- `core/serializers.py`
- `core/views.py`
- `core/migrations/0062_castnote_sort_order.py`
- `core/test_client_followup_updates.py`
- `frontend/src/api.js`
- `frontend/src/pages/op/CastNotes.vue`
- `frontend/src/pages/op/manualData.js`

## 修正内容

- `CastNote`へ永続的な表示順を保持する`sort_order`を追加
- 既存記事は従来の表示順を保ったまま初期順を設定
- managerだけが利用できる上下移動APIを追加
- 他店舗の記事、staff権限からの並び替えを拒否
- 運営画面の一覧へドラッグハンドルと上下矢印ボタンを追加
- PC・スマートフォンのポインター操作で、ドロップ先の記事の前後へ移動
- ピン留め記事と通常記事は、それぞれのグループ内で並び替え
- 検索・ステータス・カテゴリで絞り込み中は誤操作防止のため並び替えを無効化
- 新規記事は対象グループの末尾へ追加
- ピン留め／解除した記事は移動先グループの末尾へ追加
- 操作マニュアルへ並び替え手順を追記

## migration

- `0062_castnote_sort_order`
- 既存記事や他モデルの内容を削除・変更しない
- 既存記事の並び順を`sort_order`へ移すデータmigrationを含む

## テスト結果

- 関連テスト：11件成功
- Django全テスト：301件成功
- `python3 manage.py check`：問題なし
- `python3 manage.py makemigrations --check --dry-run`：差分なし
- Vue production build：成功（481 modules transformed）
- Python構文検査：成功
- `git diff --check`：問題なし

## 残課題

- 本件に関する残課題なし

## 本番反映・ブラウザ確認

- 機能PR：#49（main `1ad178f3f5ea3c5dfd9a222dc98ed9c3e9a72c9c`）
- ドラッグ確定修正PR：#50（main `7ca85fac22c0867f03d667211652a77af104b9f3`）
- Netlify production：`main@7ca85fa`の公開を確認
- 本番APIでノート3件を新規作成でき、`sort_order`を含むAPIとmigration `0062`が利用可能なことを確認
- 実ブラウザでAをCの後ろへドラッグし、`A / B / C`から`B / C / A`へ変わることを確認
- 再読み込み後も`B / C / A`が保持されることを確認
- AをBの前へ逆方向にドラッグし、`A / B / C`へ戻ることを確認
- 上下矢印でも`A / B / C`→`A / C / B`→`A / B / C`と変更・復元できることを確認
- 検索中はドラッグ・上下ボタンが無効になることを確認
- 編集保存後に元のタイトルへ戻せることを確認
- 動作確認用ノート3件は確認後に削除し、本番にテストデータが残っていないことを再読み込みして確認
- 上記操作中のブラウザコンソールエラーは0件

## 本番反映後の手動確認事項

1. managerでノート一覧を開き、ドラッグハンドルと上下矢印が表示されること
2. PCとスマートフォンで記事をドラッグし、画面再読み込み後も順番が保持されること
3. キャスト画面で同じ順番になっていること
4. ピン留め記事が通常記事より上に表示され、各グループ内で並び替えられること
5. staffでは上下矢印が表示されず、APIからも変更できないこと
6. 検索・絞り込み中は並び替えが無効になること
