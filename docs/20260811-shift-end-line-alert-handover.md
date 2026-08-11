# GPT向け引き継ぎ: シフト終了70分前の運営LINE通知

## 変更内容

- 既存のシフト終了70分前アラートを、登録済みの運営LINEトークへ自動送信できるようにした。
- 終了70分前以降に有効な予約がある場合は送信しない。
- 通知には対象キャスト、終了予定時刻、当日の予約件数、対応済み売上を含める。
- 通知先は個人トーク、グループ、複数人トークに対応する。
- マネージャー画面に表示する使い切りコードを、通知先にしたいLINEトークから公式アカウントへ送って登録する。
- 通知先IDはAPIレスポンスや画面へ公開しない。
- LINE連携、受付終了通知、通知先、アクセストークンのいずれかが未設定の場合はfail-closedとし、外部通信も送信済みログ作成も行わない。
- 送信成功済みのシフトには重複送信しない。送信失敗時は次回定期実行で再試行できる。
- シフト終了後に古い通知を送らない。
- 既存の`send_line_reminders`コマンドへ処理を追加した。

## 変更ファイル

- `core/models.py`
- `core/migrations/0053_store_shift_end_line_alert.py`
- `core/services/line_notify.py`
- `core/services/shift_end_alerts.py`
- `core/services/shift_end_line_notifications.py`
- `core/management/commands/send_line_reminders.py`
- `core/views.py`
- `core/admin.py`
- `core/test_shift_end_line_alert.py`
- `frontend/src/pages/op/SettingsLine.vue`
- `frontend/src/pages/op/manualData.js`

## 本番で必要な設定

1. LINE DevelopersのChannel secret、Channel access token、Webhook URLをRoominkのLINE設定へ登録する。
2. 通知先にする個人トークまたは運営グループへ公式アカウントを追加する。
3. RoominkのLINE設定画面に出る8文字の連携コードを、そのトークから送信する。
4. 画面で連携済みを確認後、「シフト終了70分前」の通知をONにして保存する。
5. Heroku Scheduler等で`python3 manage.py send_line_reminders`を10分間隔以内で実行する。

## 現在の本番状態

- 2026-08-11の読み取り確認では、Herokuアプリ`roomink`にSchedulerアドオンはなく、webプロセスのみ稼働していた。
- このため、コードをデプロイしただけでは自動送信は始まらない。
- Scheduler追加は外部サービス設定となるため、このPRでは実施していない。

## テスト結果

- 既存70分前アラート＋LINE関連テスト: 14件成功
- Django全テスト（SQLite）: 236件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 変更なし
- OpenAPI validation（警告をエラー扱い）: 成功
- Python構文検査: 成功
- Vue production build: 成功
- `git diff --check`: 成功

## migration

- `0053_store_shift_end_line_alert.py`を追加した。
- 通知先、通知先種別、使い切りコード、連携日時、受付終了通知ON/OFFをStoreへ追加する。
- 既存店舗は受付終了通知OFFで作成されるため、migration直後にLINEが送信されることはない。

## 本番反映前後の手動確認

- migration `0053`の適用を確認する。
- LINE設定画面で個人トークまたはテスト用グループを登録できることを確認する。
- テスト用シフトを用い、実顧客・実キャストへ送らず運営テストトークだけで1件確認する。
- その先に予約があるシフトでは送信されないことを確認する。
- Heroku Schedulerの実行間隔と実行ログを確認する。
