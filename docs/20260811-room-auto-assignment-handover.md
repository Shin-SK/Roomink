# GPT向け引き継ぎ: 希望エリアによるルーム自動割り当て

## 変更内容

- シフト登録時にルームを未指定にすると、自動で空室を割り当てるようにした。
- キャストの第1〜第5希望エリアとルームのエリア名を照合し、希望順位の高い空室を優先する。
- 同時間帯の有効な予約または別シフトで使用中のルームは候補から除外する。
- 希望エリアに一致する空室がない場合は、未希望エリアを含む空室から表示順で割り当てる。
- 管理側がルームを明示選択した場合は、その選択を優先する。
- 通常登録、週間一括登録、シフト申請承認の3経路に同じ処理を適用した。
- 操作マニュアルへ自動選択の説明を追加した。

## 変更ファイル

- `core/services/room_assignment.py`
- `core/serializers.py`
- `core/views.py`
- `core/test_room_auto_assignment.py`
- `frontend/src/pages/op/ShiftList.vue`
- `frontend/src/pages/op/ShiftWeekly.vue`
- `frontend/src/pages/op/OpShiftRequests.vue`
- `frontend/src/pages/op/manualData.js`

## テスト結果

- 関連テスト: 7件成功
- Django全テスト（SQLite）: 231件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI validation: 成功
- Python構文検査: 成功
- Vue production build: 成功
- `npm audit --audit-level=high`: 脆弱性0件
- `git diff --check`: 成功

## migration

- この変更ではmigrationを追加していない。
- キャスト希望エリアのフィールドは先行PRのmigration `0051`を使用する。

## 残課題・手動確認事項

- 先方が各キャストの希望エリアと各ルームのエリア名を正式データへ修正する必要がある。
- 本番反映後、ルーム未指定のシフト登録とシフト申請承認を各1件ずつ確認する。
- 自動割り当ては空室候補だけを対象とするが、管理者による明示選択時の既存挙動は変更していない。
