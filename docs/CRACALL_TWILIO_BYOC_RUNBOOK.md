# クラコール SIP trunk × Twilio BYOC 開通手順

最終更新: 2026-09-19

## 結論

クラコールの番号は、外線転送ではなく次の経路でRoominkへ接続する。

```text
発信者
  → クラコール SIP trunk
  → roomink-reception.sip.jp1.twilio.com
  → Roomink voice webhook
  → roomink-reception@roomink-reception.sip.twilio.com
  → Groundwire等の受付端末
```

クラコール開通後に必要なのは、Twilio側のBYOCリソース作成、Roominkへの番号登録、環境変数設定、実通話試験である。アプリ側はこの経路を受けられる実装と読み取り専用の開通判定コマンドを備える。

## 外部合意済みの固定条件

- 2026-09-16にクラコールへ提出した接続先 `roomink-reception.sip.jp1.twilio.com` を使用する。
- ユーザーの明示承認なしに別のSIP Domainへ変更しない。
- 同じSIP Domain内で認証用途を分ける。クラコールからのINVITEはIP ACL、受付端末のREGISTERはRegistration用Credential Listを使用する。
- 呼認証へ受付端末用Credential Listを紐付けない。IP ACLと呼認証Credentialを両方設定すると、Twilioが両方を要求するためである。
- PBXの外線転送は使わない。発信者番号が変わる可能性があり、Roominkの顧客照合を壊すためである。
- Twilio BYOCでは独自SIPヘッダーがWebhookへ渡らないため、独自ヘッダーに依存しない。

## クラコールへ確認する情報

開通連絡を受けたら、次を一度に確認する。

1. 割り当てられた電話番号
2. 契約が「クラコール SIP trunk / Twilio BYOC接続」であり、PBX外線転送ではないこと
3. Twilio終端の認証方式
   - Digest認証の場合: ユーザー名とパスワード
   - IP認証の場合: クラコールの固定送信元IPアドレス
4. 着信時のSIP `From` に元の発信者番号が保持されること
5. Request-URIのuser部に着信番号が入ること
   - 期待例: `sip:+8150xxxxxxxx@roomink-reception.sip.twilio.com`
6. SIP接続先FQDNが提出済みの `roomink-reception.sip.jp1.twilio.com` と一致すること
7. 通信仕様
   - TLS/SRTPの対応可否
   - コーデック（少なくともPCMU）
   - DTMF方式
   - 同時通話チャネル数
8. 試験日時と、クラコール側でログを確認できる連絡先

## Twilio側の設定

### 1. BYOC Trunk

- Friendly Name: `Roomink Cracall Inbound`
- A Call Comes In: `https://api.roomink.net/api/webhook/twilio/voice/`
- Method: `POST`
- Call Status Changes: `https://api.roomink.net/api/webhook/twilio/status/`
- Method: `POST`
- Origination Connection Policy: 不要。今回の経路はクラコールからTwilioへの着信のみ。

### 2. 既存受付SIPドメインをBYOC終端として使用

- Domain: `roomink-reception.sip.twilio.com`
- Configure With: 上記BYOC Trunk
- SIP Registration: 有効のまま維持
- Calls Authentication: クラコール固定送信元IP専用のIP Access Control Listだけを設定
- Registrations Authentication: 既存の受付端末用Credential Listを維持
- Calls AuthenticationのCredential List Mappingは削除する。Registration用Mappingは削除しない。

### 3. クラコールへ渡す接続先

クラコールへ提出済みのFQDNは `roomink-reception.sip.jp1.twilio.com`。クラコール側・提出書類・Twilio側・Roomink側の4箇所が一致していることを確認する。

## Roomink側の設定

### 環境変数

本番に次を設定する。値そのものはこの文書へ記録しない。

```text
TWILIO_BYOC_TRUNK_SID
TWILIO_BYOC_TERMINATION_DOMAIN_SID
TWILIO_BYOC_CREDENTIAL_LIST_SID
TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID
TWILIO_FROM_PHONE
TWILIO_WEBHOOK_PUBLIC_BASE_URL=https://api.roomink.net
TWILIO_WEBHOOK_ALLOW_UNSIGNED=0
RESERVATION_LINK_BASE_URL=https://r.roomink.net
```

`TWILIO_BYOC_CREDENTIAL_LIST_SID` は空、`TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID` はクラコール固定送信元IP用ACLのSIDにする。`TWILIO_BYOC_TERMINATION_DOMAIN_SID` は既存 `roomink-reception.sip.twilio.com` のDomain SIDにする。

### 店舗データ

対象店舗へ次を登録する。

- `StorePhoneNumber.phone`: クラコール着信番号を数字のみの国内形式で登録する
- `StorePhoneNumber.source_phone`: 原番号を残す必要がある場合のみ登録する
- `StorePhoneNumber.is_active`: 本番試験時に有効化する
- 店舗の受付SIPドメイン
- 1台以上の有効かつプロビジョニング済み受付端末

同じ電話番号を複数店舗へ登録しない。

## 開通前判定

対象店舗IDを指定して、まずローカル設定とDBだけを確認する。

```bash
.venv/bin/python manage.py check_voice_readiness --store-id <STORE_ID>
```

次にTwilio APIを読み取り、Webhook、BYOC Trunk、終端ドメイン、認証マッピング、SMS番号を確認する。

```bash
.venv/bin/python manage.py check_voice_readiness --store-id <STORE_ID> --live
```

`VOICE READY (live)` が出るまで実通話試験へ進まない。このコマンドはTwilioの設定を変更しない。

## 実通話試験

次の順に試し、各段階でログと画面を確認する。

1. 登録済み顧客の携帯からクラコール番号へ発信する。
2. Roominkの通話Webhookが200とTwiMLを返す。
3. 発信者番号から既存顧客が照合される。
4. 着信番号から正しい店舗が選ばれる。
5. 正しい店舗の受付端末だけが鳴る。
6. 受付端末で応答し、双方向音声を確認する。
7. 切断後も通話履歴が画面に残る。
8. 未登録番号からも発信し、新規顧客として表示されることを確認する。
9. 受付端末を応答しない試験を行い、不在着信になることを確認する。
10. 同時通話数の契約範囲内で複数着信を確認する。

### 合格条件

- 発信者番号が別番号へ置き換わらない。
- `To` のSIP URI user部から着信番号を取得できる。
- Twilio署名検証が有効な状態でWebhookが成功する。
- 他店舗へ着信しない。
- 音声が片通話にならない。
- Twilio DebuggerとRoominkログに未解決エラーがない。

## 失敗時の切り分け

| 症状 | 最初に見る場所 |
|---|---|
| Twilioへ届かない | クラコール送信先FQDNが提出済み `roomink-reception.sip.jp1.twilio.com` と一致するか、固定IP、IP ACL、BYOC関連付け |
| 403になる | Twilio Webhook署名、公開URL、リバースプロキシのURL復元 |
| 店舗が見つからない | SIP Request-URIのuser部、`StorePhoneNumber.phone` |
| 顧客が見つからない | SIP `From`、発信者番号通知、国内番号正規化 |
| 受付端末が鳴らない | 店舗の受付SIPドメイン、端末Credential、登録状態 |
| 片通話・無音 | クラコール/TwilioのTLS・SRTP・コーデック・NAT |

## ロールバック

開通試験で重大な問題が出た場合は、対象の `StorePhoneNumber.is_active` を無効にして店舗への自動ルーティングを止める。Twilio変更前に保存したDomain設定へ戻し、受付端末のRegistration用Credential Listを維持する。クラコール側の接続先は提出済みのまま変更させない。

## 公式仕様の根拠

- Twilio BYOC: https://www.twilio.com/docs/voice/bring-your-own-carrier-byoc
- Twilio SIP着信: https://www.twilio.com/docs/voice/api/sending-sip
- Twilio SIPとTwiML: https://www.twilio.com/docs/voice/api/sip-twiml
- クラコール SIP trunk: https://clocall.jp/siptrunk/
- クラコールのTwilio BYOC対応発表: https://clocall.jp/news_event/news_service/byoctrunking/
