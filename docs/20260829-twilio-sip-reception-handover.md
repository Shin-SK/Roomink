# Twilio SIP受電対応 引き継ぎ

## 概要

- 既存のTwilio米国番号へ着信した電話を、RoominkのCTIへ記録したうえで登録済みSIP端末へ接続するようにした。
- 日本番号のRegulatory Bundle申請には変更を加えていない。
- SIP設定がない場合は端末へ接続せず、案内音声を返して安全に停止する。
- migrationは作成していない。

## 変更ファイル

- `config/settings.py`
- `core/views.py`
- `core/tests.py`
- `docs/20260829-twilio-sip-reception-handover.md`

## 実装内容

### Roomink

- 環境変数 `TWILIO_SIP_URI` を追加した。
- 正規署名を検証した後に既存の `CallLog` 作成・更新を行う。
- 発信元電話番号と顧客を照合し、既存のCTIキューへ表示する。
- Twilio公式SDKで安全なTwiMLを生成し、`<Dial><Sip>` で登録済み端末を呼び出す。
- SIP URIは `ユーザー名@*.sip.twilio.com` の形式だけを許可する。
- 顧客名にXML記号が含まれてもTwiMLが壊れない。

### Twilio

- SIP Domain: `roomink-reception.sip.twilio.com`
- SIP Registration: 有効
- Secure media: 有効
- Credential List: `Roomink Reception Devices`
- SIP username: `roomink-reception`
- SIP password: macOSキーチェーンのサービス名 `Roomink Twilio SIP` に保存
- Roominkから呼び出すAOR: `roomink-reception@roomink-reception.sip.twilio.com`
- 端末の登録先: `roomink-reception.sip.tokyo.twilio.com`

同じAORで最大10台を登録でき、Twilioは登録済み端末を同時に鳴らす。最初の確認アプリは無料のLinphoneを使用する。

## 必須環境変数

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_PHONE=+15075800167`
- `TWILIO_SIP_URI=roomink-reception@roomink-reception.sip.twilio.com`（任意。未設定時も同じRoomink専用AORを使用）
- `TWILIO_WEBHOOK_PUBLIC_BASE_URL=https://roomink.netlify.app`
- `TWILIO_WEBHOOK_ALLOW_UNSIGNED=0`
- `SMS_DUMMY_MODE=0`（実送信を行う本番のみ）

`TWILIO_AUTH_TOKEN` はWebhook署名検証にも使用するため、未設定時はfail-closedでWebhookを拒否する。

## 自動検査結果

- Twilio Webhook関連テスト: 12件成功
- Django全テスト（SQLite一時DB）: 306件成功
- `python3 manage.py check`: 成功
- `python3 manage.py makemigrations --check --dry-run`: 変更なし
- Python構文検査: 成功
- Vue production build: 成功（481 modules）

## 本番反映後の実回線確認

次は自動検査とは別に、管理するテスト端末だけで実施する。

1. LinphoneでThird-Party SIP Accountを追加し、東京エッジへ登録する。
2. Twilio番号 `+1 507-580-0167` へ直接発信する。
3. RoominkのCTI表示、Linphone着信、応答、双方向音声、終話状態を確認する。
4. Linphoneを前面・バックグラウンド・画面ロックの各状態で確認する。
5. 実際の受付090から国際番号への転送可否を契約キャリアへ確認し、可能な場合だけ転送テストする。
6. 管理するテスト電話番号へSMSを1通送り、送達とRoominkのSMSログを確認する。

## 残課題・注意事項

- Heroku CLIは別アカウントでログイン中だが、SIP URIは非秘密のRoomink専用AORを安全な既定値にしたため、本番受電確認のブロッカーではない。将来別AORへ切り替える場合はConfig Varで上書きする。
- LinphoneのiOSバックグラウンド・画面ロック着信は、実機確認が完了するまで本番運用可能とは判定しない。
- 既存090から米国番号への転送は国際転送扱いになる可能性があり、キャリア側の対応・料金確認が必要。
- 日本番号の申請は並行継続し、承認後に日本番号へ切り替えるか別途判断する。
