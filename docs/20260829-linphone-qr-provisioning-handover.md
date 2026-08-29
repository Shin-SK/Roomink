# Linphone QRプロビジョニング 引き継ぎ報告

## 目的

受付担当者がTwilio SIPのDomainやTLSを手入力せず、LinphoneでQRコードを読むだけで受付電話を設定できるようにする。

## 変更ファイル

- `core/models.py`
- `core/migrations/0063_store_sip_settings_sipprovisioninglink.py`
- `core/views.py`
- `core/urls.py`
- `core/serializers.py`
- `core/tests.py`
- `core/test_sip_provisioning.py`
- `frontend/src/api.js`
- `frontend/src/pages/op/SettingsPhones.vue`
- `frontend/src/pages/op/manualData.js`
- `frontend/package.json`
- `frontend/package-lock.json`
- `docs/20260829-roomink-task-list.md`

## 実装内容

- 店舗ごとにSIP ID、SIPパスワード、Twilio SIP Domainを保持する。
- SIPパスワードは設定取得API、QR発行API、通常Serializerの読み取り応答へ含めない。
- managerだけが所属店舗のSIP設定を保存し、設定用QRを発行できる。
- QRにはSIPパスワードではなく、ランダムな短時間プロビジョニングURLを入れる。
- URLは10分で失効し、正常取得後は再利用できない。
- Linphone公式のremote provisioning XMLとしてTLS、東京Edge、ID、パスワードを設定する。
- Twilio voice webhookは着信番号から特定した店舗のSIP URIを優先し、未設定店舗のみ既存の環境設定へフォールバックする。
- 設定画面と操作マニュアルへQR設定手順を追加した。

## セキュリティ要件

- manager限定
- 所属店舗以外の設定は取得・更新不可
- QR URLの生トークンはDBへ保存せずSHA-256ハッシュのみ保存
- XML応答は `Cache-Control: no-store` とし、検索エンジンへ登録させない
- 無効・期限切れ・使用済みURLは設定情報を返さない
- Twilio webhook署名検証は既存のfail-closedを維持

## 実行済み検査

- QR・全権限・Twilio webhook・OpenAPI関連テスト: 29件成功
- Django全テスト（SQLite一時DB）: 315件成功
- OpenAPI validation（fail-on-warn）: 成功
- `python3 manage.py check`: 成功
- `python3 manage.py makemigrations --check --dry-run`: 差分なし
- Python構文検査: 成功
- Vue production build: 成功（531 modules）
- `npm audit --audit-level=high`: 0件
- `git diff --check`: 成功

権限確認ではmanagerのみ設定・QR発行を許可し、staff・cast・customer・匿名を拒否した。店舗別設定と、無効・期限切れ・使用済みURLで情報が返らないことも自動テスト済み。

## 本番確認事項

- migration `0063`の適用
- R's SPA所属managerでSIP情報を保存
- QR発行、Linphone実機読み取り、Twilio登録成功
- 海外仮番号への着信、CTI CallLog、Linphone着信、双方向音声
- iPhoneの画面ロック、バックグラウンド、アプリ終了状態の着信差異
- 管理されたテスト番号へのSMS実送信

## 未完了

- 本番デプロイおよび実機スモーク結果は、反映完了後に本書へ追記する。
- 日本番号の規制審査は別件として継続する。

---

## 2026-08-29 Groundwire移行追記

iPhoneのバックグラウンド・アプリ終了中でもPush着信できる受付アプリとして、LinphoneからGroundwireへ切り替えた。

### 変更内容

- Twilio SIP、CTI webhook、店舗別SIP設定は変更していない。
- 10分・1回限りの設定用URLを `/api/provisioning/groundwire/<token>/` で発行する。
- QRはiPhone標準カメラで読み取り、Groundwire用設定ページを開く。
- 設定ページではタイトル、ユーザー名、パスワード、Domain、TLS、東京Proxyをワンタップでコピーできる。
- 認証情報を含むページへ `no-store`、`noindex`、`no-referrer`、制限付きCSPを設定した。
- Groundwireの非公開QR形式は推測せず、公式に案内されているNew SIP Account入力方式を採用した。
- migrationと依存追加はない。

### 検証結果

- Groundwire設定・権限・店舗分離・使い切りURL関連テスト: 8件成功
- Django全テスト: 315件成功（SQLite一時テストDB）
- `python3 manage.py check`: 問題なし
- `python3 manage.py makemigrations --check --dry-run`: 変更なし
- Python構文検査: 成功
- Vue production build: 成功
- `git diff --check`: 成功

### 実機確認事項

- Groundwireでアカウント表示が緑色になること
- 通知、マイク、CallKitを許可すること
- 前面、バックグラウンド、画面ロック、アプリ終了中の着信
- Wi-Fiとモバイル回線の着信・双方向音声
- Roomink CTI表示、CallLog、終話状態
- 複数端末の同時着信と、最初の応答後に他端末が停止すること
- 1台へ複数店舗アカウントを登録した場合の店舗名表示

---

## 2026-08-29 受付端末別SIP認証追記

店舗共通のSIP認証共有をやめ、受付端末ごとの認証発行・個別停止へ変更した。

### 変更内容

- `SipReceptionDevice`で店舗、端末名、固有SIP ID、Twilio Credential SID、状態を管理する。
- 端末追加時にTwilio Credential Listへ固有IDとランダムパスワードを作成する。
- 1店舗の有効端末は、同時発信先の上限に合わせて最大10台とする。
- 端末追加・QR再発行ごとに、10分・1回限りのGroundwire設定URLを発行する。
- 設定画面を一度表示した後、Roomink DBから初期設定パスワードを消去する。
- QR再発行では対象端末のTwilioパスワードだけを変更し、古い設定を無効にする。
- 利用停止ではRoominkの着信対象から即時除外した後、Twilio Credentialを削除する。
- Twilio削除失敗時もRoomink側はfail-closedで停止し、管理画面から削除を再試行できる。
- 着信TwiMLへ有効端末を複数の`<Sip>`として出力し、同時着信させる。
- 端末管理開始後は、全端末を停止しても旧共有SIPへフォールバックしない。
- 初回端末のQR設定が完了するまでは旧受付先を維持し、設定途中の着信停止を避ける。
- managerのみ操作でき、別店舗の端末IDを直接指定しても404とする。

### 追加migration

- `0064_sipreceptiondevice_and_link_device`
- 新規端末テーブルと、使い切りリンクから端末を参照するnullable外部キーのみ追加する。

### 必須環境変数

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_SIP_CREDENTIAL_LIST_SID`（Roomink本番値を既定値として設定済み。別Twilioアカウントでは上書き必須）
- `TWILIO_WEBHOOK_PUBLIC_BASE_URL`

Twilio Consoleで、Credential ListをRoominkが使用するSIP Domainへ紐付ける必要がある。

### 検証結果

- 端末別・権限・店舗分離・使い切りQR・個別停止を含む関連テスト: 28件成功
- 複数端末TwiML、停止端末除外、全停止時fail-closed: 成功
- Django全テスト: 323件成功
- `python3 manage.py check`: 成功
- `python3 manage.py makemigrations --check --dry-run`: 変更なし
- Python構文検査: 成功
- Vue production build: 成功（531 modules）
- `git diff --check`: 成功

### 未実施・本番前確認

- 本番デプロイとmigration `0064`適用
- Roomink本番では既定のCredential List SIDを使用。別Twilioアカウントへ移す場合はHerokuで上書きする
- Twilio実APIによるCredential作成・更新・削除
- Groundwireの前面・バックグラウンド・画面ロック・アプリ終了中の実機着信
- 2台以上の同時着信、最初の応答後の他端末停止、1台だけ利用停止した場合の継続着信
- 双方向音声、Roomink CTI表示、CallLog、終話状態
