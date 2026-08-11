# キャスト希望エリア順位 引き継ぎ報告

## 概要

キャスト基本情報へ、希望エリアを第1希望から第5希望まで順番付きで登録する機能を追加した。

- 既存の `Room.area_name` と同じ自由入力形式を使用する。
- キャスト編集画面では、ルームに登録済みのエリア名を入力候補として表示する。
- 希望数が5件未満の場合は、後続順位を空欄にできる。
- 順位の途中を空けた入力と、同一エリアの重複登録は拒否する。
- 変更できるのはmanagerだけで、staff / castからの変更は拒否する。
- APIの店舗絞り込みを維持し、他店舗キャストは更新できない。

## 変更ファイル

- `core/models.py`
- `core/serializers.py`
- `core/admin.py`
- `core/migrations/0051_cast_preferred_areas.py`
- `core/test_cast_area_preferences.py`
- `frontend/src/pages/op/SettingsCasts.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/20260811-cast-area-preferences-handover.md`

## 画面と保存方法

- 画面: `/op/settings/casts`
- キャスト追加・編集モーダルへ「希望エリア」欄を追加した。
- 第1希望から第5希望まで入力できる。
- キャスト一覧の名前の下へ、登録済み順位を `第1希望 ＞ 第2希望` の順で表示する。
- ルーム管理で登録したエリアを候補表示するが、将来の希望エリアも自由入力できる。

## API・権限

既存の `POST /api/casts/` と `PATCH /api/casts/<id>/` を利用する。

追加フィールド:

- `preferred_area_1`
- `preferred_area_2`
- `preferred_area_3`
- `preferred_area_4`
- `preferred_area_5`

希望エリアのいずれかを送信した場合、manager以外は403となる。既存の店舗絞り込みにより、別店舗のキャストIDは404となる。

## migration

- `0051_cast_preferred_areas`
- `Cast`へ空文字を既定値とする5つの文字列フィールドを追加する。
- 既存キャストのデータ変換はなく、既存レコードはすべて希望未設定として維持される。

## 実行結果

- テスト先行で未実装時の失敗を確認済み。
- 関連テスト: 4件成功。
- Django全テスト SQLite: 224件成功。
- `manage.py check`: 成功。
- `makemigrations --check --dry-run`: 変更なし。
- OpenAPI validation `--fail-on-warn`: 成功。
- Python構文検査: 成功。
- Python依存整合性: 問題なし。
- `pip-audit`: 既知脆弱性0件。
- `npm audit --audit-level=high`: 既知脆弱性0件。
- Vue production build: 成功。
- `git diff --check`: 成功。

PostgreSQL 17の全テストは、PRのGitHub Actionsにある使い捨てテストDBで実行する。

## 本番反映後の手動確認

1. Heroku release phaseでmigration `0051`が成功すること。
2. managerでキャスト管理画面を開くこと。
3. テスト用キャストへ第1希望から第5希望を登録し、一覧と再編集画面へ同じ順番で表示されること。
4. 希望を減らした場合に後続順位が空欄で保存されること。
5. 本番の実キャスト情報は、先方確認後に入力すること。

## 残課題

- 希望順位を使ったルーム自動割り当ては今回の対象外。現在は運営がシフト・ルームを決める際の参考情報として保存・表示する。
- 特定日だけの希望は、既存のシフト申請メモを利用する。
