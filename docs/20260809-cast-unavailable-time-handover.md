# 予約不可時間 — GPT向け引き継ぎ

## 変更ファイル

- `core/models.py`
- `core/migrations/0046_cast_unavailable_time.py`
- `core/permissions.py`
- `core/serializers.py`
- `core/services/order_availability.py`
- `core/views.py`
- `core/urls.py`
- `core/test_cast_unavailable_time.py`
- `frontend/src/api.js`
- `frontend/src/components/UnavailableTimeModal.vue`
- `frontend/src/components/TimelineGrid.vue`
- `frontend/src/pages/op/Schedule.vue`
- `frontend/src/assets/css/components/_schedule.scss`
- `frontend/src/pages/op/manualData.js`

## 修正内容

- キャスト単位の予約不可時間モデルを追加した。
- 種別は休憩・遅刻・早退・中抜け・店舗都合・その他の固定値とした。
- manager / staffだけが登録・変更・削除できるAPIを追加した。
- 登録者・最終更新者と作成・更新日時を保存する。
- 予約不可時間は出勤シフト内だけに制限した。
- 既存の有効予約や別の予約不可時間との重複を拒否する。
- 予約作成・予約時間変更・延長時に予約不可時間との重複を拒否する。
- 顧客向け空き枠から予約不可時間を除外する。
- 運営タイムラインへ予約不可時間を斜線表示し、同画面から追加・編集・削除できるようにした。
- 24時以降は既存の営業日時基盤に合わせ、最大29:00の拡張時刻で入力できる。
- リポジトリ内の操作マニュアルへ利用方法を追加した。

## Migration

- `0046_cast_unavailable_time.py`
- 新規テーブルの作成だけで、既存データの更新・変換は行わない。
- Herokuでは従来どおりrelease phaseで適用する想定。

## テスト

- manager / staffの登録・更新と監査ユーザー保存。
- castからの登録・更新拒否。
- 他店舗データの非表示と他店舗キャスト指定拒否。
- シフト外・既存予約重複・予約不可時間重複の拒否。
- キャンセル済み予約との重複は登録可能。
- 予約作成・変更・延長の重複拒否とDB非更新。
- 顧客向け空き枠からの除外。
- タイムラインAPIへの表示。
- 25:00〜26:00の深夜帯登録。

## 検証結果

- 予約不可時間・延長・営業日関連テスト: 30件成功。
- Django全テスト（SQLite）: 160件成功。
- `manage.py check`: 問題なし。
- `makemigrations --check --dry-run`: 追加差分なし。
- OpenAPI検証: 警告・エラーなし。
- Python構文検査・依存整合性検査: 成功。
- Vue production build: 成功。
- npm High/Critical監査: 0件。
- PostgreSQL全テスト: GitHub Actionsで確認する。

## 対象外・残課題

- キャスト本人からの申請・承認フロー。
- ルーム単位・店舗全体の予約不可時間。
- 繰り返し登録。
- LINE等への自動通知。
- 同時リクエスト競合をDB制約で完全に直列化する対応。

## 手動確認事項

- 予約タイムラインの「予約不可時間」から登録・編集・削除できること。
- 登録した時間が対象キャスト行へ斜線表示されること。
- 既存予約と重なる登録で分かりやすいエラーが表示されること。
- 24時超え営業で25:00等の入力・表示が崩れないこと。
- migration適用後も既存予約・シフト・延長操作が維持されること。
