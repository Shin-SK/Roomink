# クラコール × Twilio BYOC 開通反映メモ（2026-09-25）

> **訂正（2026-09-25）**: 本メモに記載した `roomink-clocall.sip.twilio.com` への分離は、2026-09-16にクラコールへ提出済みの `roomink-reception.sip.jp1.twilio.com` と矛盾する無承認の設計変更だった。クラコール側は提出内容どおり正しく設定している。以降は提出済み接続先を固定条件とし、既存 `roomink-reception` DomainへBYOCとクラコール用IP ACLを関連付ける。下記の分離構成は事故記録として残し、正しい最終構成とは扱わない。

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
- Django全テスト: 386件合格
- `check_voice_readiness --store-id 35`: `VOICE READY (local)`
- Twilio APIでBYOC Trunk、Termination SIP Domain、IP ACL、Mappingの永続化と関連付けを再取得して確認済み

## 復旧直前の本番スナップショット

2026-09-25の復旧前に、Twilio APIとRoomink本番DBから次の状態を読み取り確認した。秘密情報や電話番号全体は記録しない。

- `roomink-reception.sip.twilio.com`
  - SIP Registration: 有効
  - BYOC Trunk: 未関連付け
  - Calls Authentication: 受付端末用Credential Listが関連付け済み、IP ACLなし
  - Registrations Authentication: 受付端末用Credential Listが関連付け済み
- `roomink-clocall.sip.twilio.com`
  - SIP Registration: 無効
  - BYOC Trunk: 関連付け済み
  - Calls Authentication: クラコール固定IP用ACLのみ
- Roomink store 35
  - 受付SIP Domain: `roomink-reception.sip.twilio.com`
  - 正式番号と米国テスト番号: 有効
  - 受付端末: 1台が有効

復旧では `roomink-reception` へBYOC Trunkとクラコール固定IP用ACLを関連付け、Calls AuthenticationだけからCredential Listを外す。Registrations AuthenticationのCredential ListとSIP Registrationは維持する。`roomink-clocall` は即時削除せず、復旧確認が完了するまでロールバック用に残す。

## 実通話で判明した受付端末呼出し条件

復旧後の正式番号への試験発信では、RoominkのCallLogとwebhookログが作られる前にTwilioエラー32209（Secure transport required）が発生した。クラコールの提出仕様はSIP 5060であり、共用SIP DomainのSecure Media強制がクラコールからのUDP着信を拒否していた。

同一Domain構成を成立させるため、Domain全体のSecure Media強制は無効にしてクラコールのUDP/5060を受ける。一方、GroundwireはTLS登録を維持し、Roominkが返す `<Dial><Sip>` の宛先も `sip:<AOR>;transport=tls` として受付端末へのSIPシグナリングはTLSを明示する。開通判定では、提出済みDomainがSecure Media強制になっていないことも検査する。

## 誤ってクラコール側へ依頼した切替（撤回）

Twilio電話認証完了後、クラコールへ次を依頼する。

1. 携帯電話への一時転送を解除する。
2. ~~正式番号への着信SIP INVITEを `roomink-clocall.sip.jp1.twilio.com` へ送る。~~ この依頼は誤り。提出済みの `roomink-reception.sip.jp1.twilio.com` を維持する。
3. Request-URIのuser部へ着信した正式番号を含める。
4. SIP `From` に元の発信者番号を保持する。
5. G.711 / RFC2833 / SIP 5060で切り替える。

グローバルURIを追加する場合も、提出済みDomainと同じ `roomink-reception.sip.twilio.com` を使用する。別Domainを追加・指定しない。

## 切替後の実回線確認

1. 登録済み顧客番号から正式番号へ発信し、顧客名案内、受付端末着信、双方向音声、終話状態を確認する。
2. 未登録番号から発信し、汎用案内、CTI新規着信、受付端末着信を確認する。
3. 受付端末で応答しない場合に、30秒後のno-answerがRoominkへ反映されることを確認する。
4. Twilio Voice Logs / DebuggerとHerokuログに認証失敗、Webhook失敗、片通話がないことを確認する。
5. 問題があればクラコール正式番号の `StorePhoneNumber.is_active` を無効化し、既存の米国テスト番号と受付SIP設定は維持する。
