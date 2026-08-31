# Roomink アプリ内サポート MVP 引き継ぎ

作成日: 2026-08-31

## 概要

Roominkへ、ログイン済み利用者向けの操作案内と、解決しなかった問い合わせを運営へ引き継ぐ第一段階を追加した。一般的なサポート運用に合わせ、次の三軸を分離している。

1. AIによる操作Q&A
2. 追加案内でも解決しない場合の運営問い合わせ
3. 現在の困りごととは分けて受け付ける「ご意見・機能要望」

- manager / staff / cast / customer のログイン後画面に「お困りですか？」を表示
- 現在の画面、権限、店舗に合わせて操作方法を回答
- 電話番号、メールアドレス、パスワードらしき文字列をAI送信前・DB保存前にマスキング
- AI未設定またはAI障害時も、内蔵の操作案内で継続動作
- 解決・未解決を記録
- 「解決しなかった」場合は理由を入力し、AIが別の確認方法を追加回答
- 追加回答でも解決しなかった場合だけ、利用者が明示的に運営問い合わせを作成
- 追加回答前の直接問い合わせはAPI側でも拒否
- 同じ店舗・権限・画面で別利用者3人の未解決評価が14日以内に蓄積した場合だけ改善候補を通知
- 「ご意見・機能要望」はAI Q&Aや現在の困りごとと分離し、実装時期を約束せず受付
- 通常問い合わせと機能要望はDB上でも種別を分離し、manager一覧で判別可能
- 未解決問い合わせを店舗別に保存
- 利用者はアプリ内の「問い合わせ履歴」から返信を確認可能
- manager専用の問い合わせ一覧を追加
- managerはAI返信案の修正・送信、自動返信停止が可能
- Slack Incoming Webhook設定時だけ明示的な問い合わせ・改善候補を通知
- 安全な操作案内に限定し、確認期限後のアプリ内自動返信を設定で有効化可能
- AIは案内だけを行い、予約・売上・給与・アカウント・SMS・LINE等の更新や実送信は行わない

## 変更ファイル

- `core/models.py`
- `core/migrations/0065_supportconversation_supportmessage.py`
- `core/services/support_assistant.py`
- `core/management/commands/process_support_auto_replies.py`
- `core/support_views.py`
- `core/urls.py`
- `core/admin.py`
- `core/test_support_assistant.py`
- `config/settings.py`
- `frontend/src/App.vue`
- `frontend/src/api.js`
- `frontend/src/router.js`
- `frontend/src/components/LayoutOperator.vue`
- `frontend/src/components/SupportAssistant.vue`
- `frontend/src/pages/op/SupportInbox.vue`

## 必要な環境変数

### AI回答を有効にする場合

- `OPENAI_API_KEY`: OpenAI API key
- `OPENAI_SUPPORT_MODEL`: 任意。未設定時は `gpt-5-mini`
- `OPENAI_SUPPORT_API_URL`: 通常は未設定でよい

API送信では `store: false` を指定している。AI未設定時は内蔵案内へ自動フォールバックする。

### Slack通知を有効にする場合

- `SUPPORT_SLACK_WEBHOOK_URL`: 問い合わせ通知先のIncoming Webhook URL

未設定でも問い合わせはDBに保存され、managerの「問い合わせ」画面で確認できる。

### 確認期限後の自動返信を有効にする場合

- `SUPPORT_AUTO_REPLY_ENABLED=1`
- `SUPPORT_AUTO_REPLY_DELAY_MINUTES`: 未設定時30分、最小5分

`python3 manage.py process_support_auto_replies` を5分間隔程度で実行する。初期値は無効であり、OpenAI・Slack・管理画面での停止操作を本番確認するまでは有効化しない。

自動返信候補は、OpenAI回答・根拠あり・操作案内・機密語句なしの場合に限定する。契約、料金、請求、個人情報、データ変更、不具合、売上、給与、権限等は自動送信しない。

## セキュリティ・権限

- 全APIはログイン必須
- managerの問い合わせ一覧は所属店舗だけ取得可能
- 他店舗IDを直接指定しても404/403となる
- customerは自分に紐づく店舗だけでサポートを利用可能
- cast向けノートは本人対象または全員対象だけを回答根拠に利用
- 1ユーザーあたり1時間30質問まで
- AIへユーザー名、顧客レコード、電話番号、メール、パスワードを送らない
- AI・Slackに業務データの更新権限を与えていない

## 実行した検証

- サポート専用APIテスト: 14件成功
- Django全テスト: 338件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: 差分なし
- OpenAPI validation: 成功
- Vue production build: 成功
- `git diff --check`: 成功

## 手動確認事項

- migration `0065` 適用後、各権限で右下ボタンが表示されること
- 公開予約、ログイン、パスワード案内画面には表示されないこと
- スマートフォンでチャットパネルが画面内に収まること
- `質問 → 解決しなかった理由 → AI追加回答 → 運営へ問い合わせる` の表示と操作を確認すること
- 「ご意見・機能要望」が通常問い合わせと別画面で受け付けられ、manager一覧で「機能要望」と表示されること
- managerのサイドバー「問い合わせ」から所属店舗の問い合わせだけ見えること
- OpenAI API key設定後、AI回答とフォールバックの両方を確認すること
- Slack Webhook設定後、テスト問い合わせ1件だけで通知とリンクを確認すること
- 自動返信を有効にする前に、Slack通知、返信案修正、停止、自動送信、利用者履歴への表示をテストアカウントで確認すること

## 残課題

- OpenAI API keyの本番設定
- Slack通知先とIncoming Webhookの作成・本番設定
- 操作マニュアルの全記事を検索対象へ同期する仕組み
- メールは問い合わせ本体にせず、アプリ内返信が届いたことを知らせる通知として追加検討
- Slack上の承認ボタンはIncoming Webhookだけでは実現できないため、必要ならSlack Appとして追加
- managerが正式回答をFAQ候補へ昇格・承認する機能
- 本番デプロイ後の権限別ブラウザ確認
