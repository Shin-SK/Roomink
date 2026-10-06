# Roomink運営公式LINE受信箱

この機能は、Roomink運営用の公式LINEに届いた問い合わせを保存し、Codexが後から
読み取るためだけの受信箱です。自動返信、LINE送信、Slack通知、案件自動作成は行いません。
既存の店舗LINE Webhookと同じ公式アカウントに設定してはいけません。

## 本番設定（ステージング合格・本番承認後のみ）

Roominkの該当環境に次を設定する。値はリポジトリ、ログ、LINE本文に残さない。

```text
OPERATIONS_LINE_INBOX_ENABLED=1
OPERATIONS_LINE_INBOX_CHANNEL_SECRET=...
OPERATIONS_LINE_INBOX_CHANNEL_ACCESS_TOKEN=...
OPERATIONS_LINE_INBOX_READ_TOKEN=<十分に長いランダム値>
OPERATIONS_LINE_INBOX_RETENTION_DAYS=30
OPERATIONS_LINE_INBOX_MAX_ATTACHMENT_BYTES=52428800
```

運営公式LINEのMessaging API Webhook URLを次へ設定し、LINE Developersで検証する。

```text
https://api.roomink.net/api/webhook/operations-line-inbox/
```

このURLを有効にした時点より後の受信だけが対象で、過去のテキストは取得できない。
画像・動画・音声・ファイルは受信時に取得を試みる。動画と音声はLINE側の準備中に
`PENDING` となることがあり、Codexが添付を開く際にもう一度だけ取得を試みる。

添付は外部ストレージを新設せずRoomink PostgreSQLに保存する。既定で30日後に受信または
閲覧処理のタイミングで削除する。添付取り消し（unsend）を受けた場合は本文と添付本体を
直ちに消す。上限を超えるファイルは保存せず `TOO_LARGE` と表示する。

## Codexからの読む手順

Codexを動かすMacにだけ、次を設定する。

```text
ROOMINK_LINE_INBOX_API_BASE_URL=https://api.roomink.net/api
ROOMINK_LINE_INBOX_READ_TOKEN=<OPERATIONS_LINE_INBOX_READ_TOKENと同じ値>
```

受信内容だけを表示する。

```bash
node tools/read_operations_line_inbox.mjs --limit=20
```

画像・動画・音声・ファイルもローカルに保存して確認する。

```bash
node tools/read_operations_line_inbox.mjs \
  --limit=20 \
  --download-dir=/tmp/roomink-line-inbox
```

このCLIにはLINEへ送信する機能がない。返信案はCodexで作成し、送信は運営者が公式LINEで
手動で行う。
