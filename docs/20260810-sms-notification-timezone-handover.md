# GPT引き継ぎ報告書：SMS通知時刻の店舗タイムゾーン統一

## 概要

本番スモークで、予約画面は日本時間を表示している一方、SMS送信履歴の本文がUTCのまま9時間ずれて表示される問題を修正した。予約データや画面表示は変更せず、通知本文を作る直前に店舗のタイムゾーンへ変換する。

## 変更ファイル

- `core/services/notify.py`
- `core/test_notification_timezone.py`
- `core/test_order_extension_duration.py`
- `docs/20260810-sms-notification-timezone-handover.md`

## 修正内容

- 予約の開始・終了日時を`Store.timezone`へ変換する共通処理を追加した。
- 店舗タイムゾーンが無効な場合はDjangoの標準タイムゾーンへフォールバックする。
- 次の通知経路を店舗時刻へ統一した。
  - 店舗設定の予約確認SMSテンプレート
  - テンプレート未設定時の予約確認SMS
  - キャスト向け予約通知
  - 顧客向けキャンセル通知
- UTCの`03:00〜04:30`が、`Asia/Tokyo`店舗では`12:00〜13:30`になる回帰テストを追加した。
- 固定日付が過去日になったことで失敗していた既存のstaff延長テストは、検証対象日時だけをテスト内で固定した。業務コードや権限仕様は変更していない。

## 影響範囲

- DB保存値、予約日時、画面表示、API形式は変更しない。
- migrationはない。
- Twilio設定や送信条件は変更しない。
- 実電話番号・実SMSは使用していない。

## テスト結果

- 追加回帰テスト：4件成功
- 日付依存テストとの関連確認：計5件成功
- Django全テスト（SQLite）：174件成功
- `manage.py check`：成功
- `makemigrations --check --dry-run`：追加差分なし
- OpenAPI validation（fail-on-warn）：成功
- Python構文検査：成功
- Python依存整合性：成功
- Vue production build：成功
- `npm audit --audit-level=high`：脆弱性0件
- `git diff --check`：成功

PostgreSQL 17の全テストはGitHub Actionsの一時テストDBで再実行し、成功をマージ条件とする。

## 本番反映後の確認

1. HerokuとNetlifyが同じmainコミットを公開していること。
2. Heroku healthが200を返すこと。
3. 保存を伴わないHeroku上の確認で、UTC 03:00の予約がAsia/Tokyoでは12:00として通知本文へ入ること。
4. Twilio未設定中は引き続き`CONFIG_MISSING`で安全停止し、実SMSを送らないこと。

## 残課題

- Twilio番号・認証情報の本番設定後に、管理されたテスト番号で実SMS文面を最終確認する。
- 数字だけのstaffユーザー名が電話番号ログインとして正規化される問題は別案件で扱う。
