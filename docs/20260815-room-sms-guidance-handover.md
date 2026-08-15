# ルーム別SMS案内 引き継ぎ報告

## 対象

予約に割り当てられたルームに応じて、住所・地図URL・注意事項を予約確認SMSへ差し込めるようにする対応。

## 変更ファイル

- `core/models.py`
- `core/services/notify.py`
- `core/migrations/0054_room_map_url_room_sms_notice.py`
- `core/test_room_sms_guidance.py`
- `frontend/src/pages/op/SettingsRooms.vue`
- `frontend/src/pages/op/SettingsSmsTemplates.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/20260815-room-sms-guidance-handover.md`

## 修正内容

- `Room`へ任意入力の`map_url`と`sms_notice`を追加した。
- ルーム管理画面から、住所・地図URL・SMS注意事項を登録・編集できるようにした。
- SMSテンプレートへ次の差し込み項目を追加した。
  - `{room_address}`: ルーム住所
  - `{room_map_url}`: 地図URL
  - `{room_notice}`: ルーム固有の注意事項
  - `{room_guidance}`: ルーム名・住所・地図・注意事項をまとめた案内
- SMSの既定文面へ`{room_guidance}`相当の案内を追加した。
- 予約のルームが未定の場合は「ルーム: 調整中」とし、他ルームの住所・地図・注意事項を出さない。
- 既存のルーム自動割当処理には変更を加えていない。SMSは予約へ実際に保存されたルームを参照する。
- 既存の操作マニュアルへ入力手順を追記した。

## migration

- `0054_room_map_url_room_sms_notice`を追加した。
- 既存ルームは両項目とも空欄で開始する。
- ローカルDB・本番DBへのmigration適用は行っていない。

## テスト結果

- 関連テスト: 15件成功
  - ルーム別SMS案内
  - ルーム自動割当
  - 顧客ページのルーム住所表示
- Django全テスト: 258件成功（SQLite一時テストDB）
- `manage.py check`: 問題なし
- `makemigrations --check --dry-run`: 変更なし
- Python構文検査: 成功
- Vue production build: 成功（476 modules transformed）
- `git diff --check`: 問題なし

## 本番反映前後の手動確認

1. デプロイ時にmigration `0054`が正常適用されることを確認する。
2. マネージャーで「設定 → ルーム管理」を開く。
3. 各ルームへ正式な住所・Google Maps URL・必要な注意事項を入力する。
4. 有効な独自SMSテンプレートを使用している場合は、本文へ`{room_guidance}`または個別の差し込み項目を追加する。
5. 管理されたテスト顧客・テスト電話番号で、予約に割り当てられたルームの案内だけが送られることを確認する。
6. シフト外予約などルーム未定の予約では、住所・地図・注意事項が送られないことを確認する。

## 残課題

- 正式な地図URLと注意事項は運営側の入力が必要。
- Twilioの日本番号申請が承認され、認証情報・送信元番号を本番へ設定するまでは実SMS送信を行えない。
- 現在有効な独自SMSテンプレートは自動書き換えしないため、運営側で新しい差し込み項目を追加する必要がある。
