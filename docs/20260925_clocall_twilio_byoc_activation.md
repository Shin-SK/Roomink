# クラコール × Twilio BYOC 開通反映メモ（2026-09-25）

## 実施済み

- クラコールの開通資料を確認した。
  - 正式番号は番号管理表の `0001!B5`。本メモには番号全体を残さず、末尾 `0050` のみ記録する。
  - 回線条件は1ch、G.711 / RFC2833、SIP 5060。
  - クラコール側にはTwilio東京リージョンのSIPシグナリングIPレンジが登録済み。
  - クラコールSBCの接続先IPはTwilioのIP ACLへ登録した。本メモには値を残さない。
- Twilioにクラコール専用リソースを作成した。
  - BYOC Trunk: `Roomink Clocall Inbound`
  - Termination SIP Domain: `roomink-clocall.sip.twilio.com`
  - Carrier IP ACL: `Roomink Clocall Carrier`
  - Voice Webhook: `https://api.roomink.net/api/webhook/twilio/voice/`（POST）
  - Status Callback: `https://api.roomink.net/api/webhook/twilio/status/`（POST）
- 受付端末用の `roomink-reception.sip.twilio.com` と、そのCredential Listには変更を加えていない。
- Heroku本番へBYOC SID、Termination Domain SID、Carrier IP ACL SID、受付端末Credential List SIDを設定した。
- `TWILIO_WEBHOOK_ALLOW_UNSIGNED=0` を明示し、署名検証を有効のまま維持した。
- アールズスパ（store 35）へクラコール正式番号を有効状態で追加した。
- 既存の米国テスト番号は、切替失敗時の確認経路として残した。
- クラコール正式番号のTwilio電話認証は完了した。

## 実装上の修正

Twilio Python SDK 9.4.4の実レスポンスでは、SIP DomainのIP ACL MappingはACL SIDを `mapping.sid` として返す。開通判定がテスト用モックの `ip_access_control_list_sid` だけを参照していたため、実レスポンスと互換になるよう次の順でSIDを読むよう修正した。

1. SDKやモックが専用属性を持つ場合はその値
2. 実Twilioレスポンスでは `mapping.sid`

Credential List Mappingも同じ形式に対応させた。

## 自動確認

- `python manage.py check`: 合格
- `python manage.py makemigrations --check --dry-run`: 変更なし
- Django全テスト: 385件合格
- `check_voice_readiness --store-id 35`: `VOICE READY (local)`
- Twilio APIでBYOC Trunk、Termination SIP Domain、IP ACL、Mappingの永続化と関連付けを再取得して確認済み

## クラコール側へ依頼する切替

Twilio電話認証完了後、クラコールへ次を依頼する。

1. 携帯電話への一時転送を解除する。
2. 正式番号への着信SIP INVITEを `roomink-clocall.sip.jp1.twilio.com` へ送る。
3. Request-URIのuser部へ着信した正式番号を含める。
4. SIP `From` に元の発信者番号を保持する。
5. G.711 / RFC2833 / SIP 5060で切り替える。

グローバルURIの登録が必要な場合は `roomink-clocall.sip.twilio.com` を使い、東京リージョンの利用可否をクラコール担当者と一致させる。

## 切替後の実回線確認

1. 登録済み顧客番号から正式番号へ発信し、顧客名案内、受付端末着信、双方向音声、終話状態を確認する。
2. 未登録番号から発信し、汎用案内、CTI新規着信、受付端末着信を確認する。
3. 受付端末で応答しない場合に、30秒後のno-answerがRoominkへ反映されることを確認する。
4. Twilio Voice Logs / DebuggerとHerokuログに認証失敗、Webhook失敗、片通話がないことを確認する。
5. 問題があればクラコール正式番号の `StorePhoneNumber.is_active` を無効化し、既存の米国テスト番号と受付SIP設定は維持する。

