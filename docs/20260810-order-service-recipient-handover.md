# 予約の連絡者・実利用者分離 引き継ぎ報告

## 最終判定

`PR READY / CI GREEN`

## 変更内容

- `Order.service_recipient_name` を追加した。
  - 最大50文字の名前スナップショット。
  - 空欄は「連絡者本人」を意味する。
  - 前後空白はAPI保存時に除去する。
- 既存の `Order.customer` は予約連絡者として維持した。
- manager / staff の予約作成・編集フォームへ任意入力欄を追加した。
- 運営の予約詳細・タイムライン・ダッシュボードで連絡者と実利用者を区別して表示する。
- 顧客マイページと予約詳細へ実利用者を表示する。
- 予約検索とDjango管理画面検索で実利用者名を検索可能にした。
- 売上CSVの末尾へ後方互換を保つ形で「実利用者名」列を追加した。

## 変更ファイル

- `core/models.py`
- `core/serializers.py`
- `core/views.py`
- `core/admin.py`
- `core/services/sales.py`
- `core/migrations/0048_order_service_recipient_name.py`
- `core/test_order_service_recipient.py`
- `frontend/src/components/OrderForm.vue`
- `frontend/src/components/TimelineGrid.vue`
- `frontend/src/pages/op/Dashboard.vue`
- `frontend/src/pages/op/OrderDetail.vue`
- `frontend/src/pages/cu/CuMypage.vue`
- `frontend/src/pages/cu/CuReservation.vue`

## Migration

- `0048_order_service_recipient_name`
- 既存行を更新しないadditive migration。
- 既存予約は空欄のまま保持し、表示時に「本人」と解釈する。
- 専用の空SQLite DBで全migration適用、0048逆適用、0048再適用を確認済み。
- 本番DB・既存ローカルDBには適用していない。

## データと権限の定義

- 連絡者: 従来どおり `Order.customer`。電話番号、SMS、顧客アカウント、予約所有権、売上・来店集計の基準。
- 実利用者: `Order.service_recipient_name` の文字列スナップショットのみ。
- 実利用者名からCustomerを自動作成・検索・関連付けしない。
- 同名Customerが存在しても自動関連付けしない。
- 実利用者用の電話番号・Customer FK・招待は作らない。
- 当日・未来の実利用者名変更はmanager / staffのみ。
- 過去営業日は既存ルールどおりmanagerのみ。
- customer / castは実利用者名を変更できない。
- 顧客向け予約作成APIへ実利用者名を不正送信しても空欄に固定する。

## SMS・顧客マイページ

- SMS送信先とCustomerAccountInvitationは常に連絡者Customer。
- 実利用者用のInvitationは作成しない。
- 顧客マイページの所有権判定は従来どおり `Order.customer`。
- 名前一致だけで別Customerへ予約閲覧権限を付与しない。

## 検索・集計への影響

- 予約検索: 連絡者名、連絡者電話番号、実利用者名で検索可能。
- 顧客一覧検索: 実利用者名だけの人物は表示しない。
- 売上、精算、指名料、支払、Customer来店回数は従来どおり連絡者Customer基準。
- 実利用者名追加による既存集計結果の変更なし。

## テスト結果

- 新規関連テスト: 12件成功。
- Django全テスト SQLite: 195件成功。
- `manage.py check`: 成功。
- `makemigrations --check --dry-run`: 差分なし。
- OpenAPI validation: warningなしで成功。
- Python構文検査: 成功。
- `pip check`: 成功。
- `pip-audit`: 既知脆弱性0件。
- `npm ci`: 成功。
- `npm audit --audit-level=high`: 0件。
- Vue production build: 成功。
- `git diff --check`: 成功。
- Django全テスト PostgreSQL 17: 195件成功。

## ローカルブラウザ確認

実データを使わず、専用一時DBのサンプル予約で確認した。

- managerログイン成功。
- 運営予約詳細で「連絡者」「ご利用者」を分離表示。
- 編集フォームに既存の実利用者名が復元される。
- 実利用者名の編集・保存成功（PATCH 200）。
- 顧客ログイン成功。
- 顧客予約詳細へ更新後の実利用者名が反映。
- 画面上のエラー表示・サーバー500なし。

## 対象外・残課題

- 実利用者Customerへの過去予約の手動関連付け。
- Customer統合、ポイント・指名実績・来店回数の移行。
- 実利用者用Customerの自動作成。
- 代表予約専用グループモデル。
- 一般Web予約、70分前アラート、SMS文面改修、LINE、CTI。

将来の履歴関連付けは、本人確認方法と監査要件を別途設計してから実装する。

## Git / deploy

- branch: `feat/order-service-recipient`
- PR: `#23`
- CI: GitHub Actions run #49で全4チェック成功
  - Backend checks
  - Backend tests (SQLite)
  - Backend tests (PostgreSQL 17)
  - Frontend checks
- 本番deploy: なし

## 次の推奨作業

PR #23を人間がレビューし、merge可否を判断する。本件では自動merge・本番deployは行わない。
