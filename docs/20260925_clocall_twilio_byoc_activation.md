# クラコール × Twilio BYOC 開通反映メモ（2026-09-25）

> **最終訂正（2026-09-25）**: クラコールへ提出済みの外部接続先 `roomink-reception.sip.jp1.twilio.com` は固定し、変更しない。一方、実機REGISTERではこのBYOC/IP ACL用DomainがTwilio 403 / 32200を返し、同じCredentialを独立した登録用Domainへ向けると正常な407認証要求へ進むことを再現確認した。したがって、クラコール入口は `roomink-reception` のまま、Roomink内部の受付端末だけを `roomink-devices.sip.twilio.com` へ登録する。過去の `roomink-clocall` への外部切替依頼は誤りであり、本構成とは別物である。

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
- Django全テスト: 388件合格（最終実通話修正を含む）
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

復旧では `roomink-reception` へBYOC Trunkとクラコール固定IP用ACLを関連付け、Calls AuthenticationからCredential Listを外した。その後の実機検証により、受付端末REGISTERは独立した `roomink-devices` Domainへ分離する。クラコールの接続先、BYOC Trunk、固定IP ACLは変更しない。

## 実通話で判明した受付端末呼出し条件

復旧後の正式番号への試験発信では、RoominkのCallLogとwebhookログが作られる前にTwilioエラー32209（Secure transport required）が発生した。クラコールの提出仕様はSIP 5060であり、共用SIP DomainのSecure Media強制がクラコールからのUDP着信を拒否していた。

同一Domain構成を成立させるため、Domain全体のSecure Media強制は無効にしてクラコールのUDP/5060を受ける。一方、GroundwireはTLS登録を維持し、Roominkが返す `<Dial><Sip>` の宛先も `sip:<AOR>;transport=tls` として受付端末へのSIPシグナリングはTLSを明示する。開通判定では、提出済みDomainがSecure Media強制になっていないことも検査する。

Secure Media強制解除後の実通話では、クラコールからRoominkのVoice Webhookへ到達し、正式番号に対応するCallLogが作成された。クラコールはこの試験着信の発信者番号をTwilioへ `Unavailable` として渡したため、Roominkでこれを非通知発信と同じ `anonymous` として受け入れる互換処理と再発テストを追加した。

その後、Roominkは受付端末AORへのTLS子通話を正しく生成した。Twilioの最終結果はエラー32009（登録ユーザーが現在未登録）だった。Groundwireログでは東京Proxyまで到達後、共有Domainが403 / 32200（insufficient permissions）を返していた。同じ端末Credentialを一時的な独立Domainへ割り当てたREGISTERは407認証要求へ進んだため、Groundwire・iPhone・回線ではなく、BYOC/IP ACLと端末Registrationを同一Domainへ載せた構成が原因と確定した。

最終構成は次のとおり。

- クラコール外部入口: `roomink-reception.sip.jp1.twilio.com`（提出済みのまま）
- Twilio BYOC終端: `roomink-reception.sip.twilio.com`（クラコール固定IP ACL）
- Groundwire登録先: `roomink-devices.sip.twilio.com`（受付端末Credential List）
- Roominkの端末呼出し先: `sip:<端末ユーザー名>@roomink-devices.sip.twilio.com;transport=tls`

## Groundwire初期設定の運用課題

実機では、正式な050受付番号、Groundwireへ入力するSIPアカウント、再表示できないSIPパスワードの違いが利用者に伝わりにくい。既存端末で登録エラーになった場合、利用者がどの値を直すべきか判断できないため、次の改善を本番運用前の課題として残す。

- 正式な受付番号とSIP接続IDを別物として明記する。
- アカウントを削除させず、対象端末の「QR再発行」からパスワードを更新する手順を画面内で案内する。
- QR再発行後は、ユーザー名、Domain、TLS、Proxyは原則変更せず、新しいパスワードだけを入れ直すと明記する。
- Groundwireの登録状態が緑になったことを完了条件として表示する。
- Groundwireでは、ドメイン直下の「詳細設定」を開いて「プロキシ」を入力する。「トランスポートプロトコル」は詳細設定の下部にあるため、`tls (sip)` を選ぶ場所まで案内する。
- 将来は、利用者がSIP用語や各入力値を判断しなくても済む初期設定導線を検討する。

## 誤ってクラコール側へ依頼した切替（撤回）

Twilio電話認証完了後、クラコールへ次を依頼する。

1. 携帯電話への一時転送を解除する。
2. ~~正式番号への着信SIP INVITEを `roomink-clocall.sip.jp1.twilio.com` へ送る。~~ この依頼は誤り。提出済みの `roomink-reception.sip.jp1.twilio.com` を維持する。
3. Request-URIのuser部へ着信した正式番号を含める。
4. SIP `From` に元の発信者番号を保持する。
5. G.711 / RFC2833 / SIP 5060で切り替える。

クラコール側のグローバルURIを追加する場合も、提出済みDomainと同じ `roomink-reception.sip.twilio.com` を使用する。クラコールの外部接続先として別Domainを追加・指定しない。内部受付端末用の `roomink-devices` はこの外部接続先には使用しない。

## 切替後の実回線確認

1. 登録済み顧客番号から正式番号へ発信し、顧客名案内、受付端末着信、双方向音声、終話状態を確認する。
2. 未登録番号から発信し、汎用案内、CTI新規着信、受付端末着信を確認する。
3. 受付端末で応答しない場合に、30秒後のno-answerがRoominkへ反映されることを確認する。
4. Twilio Voice Logs / DebuggerとHerokuログに認証失敗、Webhook失敗、片通話がないことを確認する。
5. 問題があればクラコール正式番号の `StorePhoneNumber.is_active` を無効化し、既存の米国テスト番号と受付SIP設定は維持する。
