# Roomink 本番化・開通準備 引き継ぎ

最終更新: 2026-09-25

## 今回の到達点

Roominkを「電話予約を受け、必要最小限のSMSで利用者を予約マイページへ案内するサービス」として整理し、次を実装した。

- ログイン不要・推測困難なトークン式の予約マイページ
- 予約内容と状態を確認できるタイムライン
- 現地決済は予約確定時のSMS 1通で完結するフロー
- カード決済は仮予約SMS、外部決済、店舗の目視確認、本予約SMSという2通のフロー
- カード決済確認前は部屋住所を表示せず、確認後に表示する制御
- SMS文面の1セグメント化、セグメント数・配信状態・月次使用量の記録
- 月額19,800円、200通分を含み、以降100通分ごとに5,000円を加算する料金表示
- テスト店舗を課金集計から除外できる設定
- ステージングと本番の設定取り違えを防ぐビルド・起動時検査
- クラコール SIP trunk とTwilio BYOCをつなぐ着信処理および開通前判定コマンド

Roominkはカード情報を保持せず、決済の実行・照合・返金をしない。店舗が外部決済を確認して予約状態を更新する。LINE連携は今回の対象外とした。

## SMSの扱い

- 料金表示上は「SMS送信数」と表現する。
- 内部ではTwilioのセグメント数を「通分」として集計する。
- 2セグメントのSMSは2通分として数える。
- SMSは外部通知、予約マイページを最新情報の正本とする。
- 通常予約では1予約1通を原則とする。
- カード決済のみ、仮予約と本予約の2通を必要経費として扱う。
- キャンセルや重大な状態変更は、取りこぼしを避けるためSMSを使用する。

## クラコール開通時の接続経路

```text
発信者
  → クラコール SIP trunk
  → roomink-reception.sip.jp1.twilio.com（クラコール固定IPで認証）
  → Roomink voice webhook
  → <受付端末ユーザー名>@roomink-devices.sip.twilio.com
  → Groundwire等の受付端末
```

2026-09-16にクラコールへ提出した接続先は `roomink-reception.sip.jp1.twilio.com` であり、これは外部合意済みの固定条件とする。クラコールからのINVITEは同DomainのIP Access Control Listで認証する。受付端末のREGISTERは、実機で共有Domainが403/32200を返すことを確認したため、内部専用 `roomink-devices.sip.twilio.com` のCredential Listで認証する。クラコール側の接続先は変更しない。独自SIPヘッダーには依存せず、標準のSIP `From` とRequest-URIから発信者番号・着信番号を取得する。

## 2026-09-25 接続先分離事故

- 2026-09-16の提出後、ユーザーの依頼・承認なしに「受付端末用とBYOC終端を分離する」という一般設計を本資料とランブックへ追加した。
- その後、`roomink-clocall.sip.twilio.com` を新設し、本番のBYOC終端を提出済み接続先から変更した。
- クラコールは提出内容どおり `roomink-reception.sip.jp1.twilio.com` へ送信していたが、この内部変更との不一致を先方の設定ミスと誤認し、接続先変更を依頼した。
- 原因はRoomink側の無承認な設計変更と、提出書類・本番設定・検査条件の照合不足であり、クラコール側の誤りではない。
- 今後、外部へ提出・合意した接続情報はユーザーの明示承認なしに変更しない。引き継ぎ資料や一般的な設計論は外部合意を上書きできない。
- 開通判定は、BYOC終端のDomainが店舗の提出済み受付Domainと一致し、クラコール用IP ACL、受付端末のSIP Registration、Registration用Credential Listが同時に成立する場合だけ合格とする。

具体的な設定、試験、失敗時の切り分けは [CRACALL_TWILIO_BYOC_RUNBOOK.md](CRACALL_TWILIO_BYOC_RUNBOOK.md) を参照する。

## 開通前判定

対象店舗の設定とTwilio上の実リソースを、次のコマンドで読み取り専用検査できる。

```bash
python manage.py check_voice_readiness --store-id <STORE_ID> --live
```

`VOICE READY (live)` が表示されるまで実通話試験へ進まない。検査対象は以下。

- Twilioアカウント、SMS送信番号
- BYOC TrunkとWebhook URL・HTTPメソッド
- BYOC終端SIPドメイン
- クラコール専用Credential ListまたはIP Access Control List
- Roominkの店舗着信番号
- 受付SIPドメイン
- 有効かつプロビジョニング済みの受付端末

## 検証結果

- Django全テスト: SQLite / PostgreSQLとも合格
- GitHub Actions: フロント、バックエンド検査、SQLite、PostgreSQLの全ジョブ合格
- Django system check、migration差分検査、OpenAPI検査: 合格
- Python / npm依存関係の脆弱性監査: 検出なし
- フロントエンド本番ビルド・ステージングビルド: 合格
- 予約マイページ: 390px幅の実ブラウザで横崩れなし
- カード仮予約・本予約の表示制御: 実ブラウザで確認
- Netlify PRプレビュー: 合格

## 本番環境の確認結果

- Web: `https://app.roomink.net`
- API: `https://api.roomink.net`
- 予約案内: `https://r.roomink.net`
- Heroku Postgres、Web dyno、ACMは稼働中
- 本番リリース `v139` で `RESERVATION_LINK_BASE_URL=https://r.roomink.net` を反映済み
- 本番ヘルスチェックは正常
- Twilioには受付端末用SIPドメインとSMS対応番号が存在する
- Twilio BYOC TrunkとBYOC終端SIPドメインは、クラコールの接続情報待ちのため未作成
- `r.roomink.net` はNetlifyのドメインエイリアスとして登録済み
- Cloudflareには `r` から `roomink.netlify.app` へのDNS-only CNAMEを登録済み
- Let's Encrypt証明書は `app.roomink.net` と `r.roomink.net` の両方を含む
- 実ブラウザで予約画面を表示し、無効トークンが安全なエラー案内になることを確認済み
- 本番URL長で、現地決済・カード仮予約・カード本予約の3文面がすべてUCS-2の1セグメントに収まることを確認済み

## クラコール回答後に必要な情報

1. 割り当て電話番号
2. SIP trunk / Twilio BYOC接続であることの確認
3. Digest認証情報、または固定送信元IP
4. SIP `From` に元の発信者番号が保持されること
5. Request-URIのuser部に着信番号が入ること
6. TwilioのFQDNを接続先に指定できること
7. TLS/SRTP、PCMU、DTMF、同時通話数
8. 実通話試験の日時とクラコール側連絡先

## 開通日に行う順序

1. クラコール回答内容を上記チェックリストと照合する。
2. Twilioの既存 `roomink-reception.sip.twilio.com` をBYOC Trunkへ関連付け、クラコール固定IPのACLを呼認証へ追加する。受付端末のRegistration認証は内部専用 `roomink-devices.sip.twilio.com` に設定する。
3. 対象店舗を確定し、着信番号をRoominkへ登録する。
4. 本番環境変数へTwilioリソースIDを設定する。
5. `check_voice_readiness --live` が合格することを確認する。
6. 登録済み番号、未登録番号、不在、同時着信の順に実通話試験を行う。
7. Twilio DebuggerとRoominkログに未解決エラーがないことを確認する。

## 利用者側で最後に必要な作業

- クラコールから届く接続情報を共有する。
- 新しい電話番号を割り当てるRoomink店舗を指定する。
- 有料の独立ステージング環境を新設する場合は、Heroku Postgres等の費用発生を承認する。

これらが揃うまでは、BYOCリソースを推測で作らず、実在する受付SIP設定も変更しない。外部へ提出済みの接続先と異なる構成を採用する場合は、実装前にユーザーの明示承認を得る。
