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
