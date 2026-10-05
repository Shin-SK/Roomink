# Roomink運営LINE受付

店舗運営者だけの公式LINEを入口にし、一次ヒアリング後にRoominkプロジェクトの
Codex案件タスクを作る。Slackは通知と承認・開始操作だけであり、案件の会話や実装を
Slackへ集約しない。

## 実際の流れ

1. 友だち追加時に、LINEが店舗名とお名前を丁寧に伺う。
2. 初回の回答はSlackへ「利用登録申請」として一度だけ通知される。
3. 運営者がSlackの`登録内容を確認`から店舗と担当者名を選び、承認する。
4. LINEは登録完了を案内し、以後は相談内容を受け付ける。
5. AIが不足情報を必要最小限だけ確認する。要件がそろうと、Codex bridgeへ
   `CREATE_THREAD`を待機させる。
6. ローカルMacのbridgeがRoominkプロジェクト内に案件別Codexタスクを作り、
   Slackへ`Codexで案件を開く`と`修正開始`を通知する。
7. 詳しい確認は案件タスクで行う。すぐ対応してよいものは、Slackの`修正開始`で
   実際のCodex作業を起動する。
8. 完了後のNotion記録は、従来どおり作業の総括として手動で残す。

## セキュリティと正直な状態表示

- LINEとSlackのwebhookは、それぞれの署名を必ず検証する。
- Codexは外部公開しない。bridgeはRoomink APIをBearer tokenでポーリングするだけ。
- bridgeが停止中なら案件は`起動待ち`に留まる。LINEへ作業開始済みとは返信しない。
- 案件ごとのgit worktreeを作るため、複数案件が同じ作業ディレクトリを競合しない。

## 本番設定（リリース承認後のみ）

HerokuのRoomink環境に、次を設定する。値はリポジトリやSlack本文に書かない。

```text
OPERATIONS_LINE_INTAKE_ENABLED=1
OPERATIONS_LINE_CHANNEL_ACCESS_TOKEN=...
OPERATIONS_LINE_CHANNEL_SECRET=...
OPERATIONS_SLACK_BOT_TOKEN=...
OPERATIONS_SLACK_CHANNEL_ID=...
OPERATIONS_SLACK_SIGNING_SECRET=...
OPERATIONS_CODEX_BRIDGE_TOKEN=<十分に長いランダム値>
```

公式LINEのWebhook URLは`/api/webhook/operations-line/`、Slack Interactivityの
Request URLは`/api/webhook/operations-slack/`にする。どちらもまずステージングで
確認してから本番へ切り替える。

## ローカルbridge

Codexを動かすMacにだけ、次を環境変数として設定する。

```text
ROOMINK_OPS_API_BASE_URL=https://<Roomink API>/api
ROOMINK_OPS_BRIDGE_TOKEN=<OPERATIONS_CODEX_BRIDGE_TOKENと同じ値>
ROOMINK_CODEX_PROJECT_ID=<Codex App ServerのRoomink project ID>
ROOMINK_OPS_REPOSITORY=<Roominkのgit root>
ROOMINK_OPS_WORKTREE_ROOT=<案件別worktreeを置く親ディレクトリ>
ROOMINK_CODEX_CLI=/Applications/ChatGPT.app/Contents/Resources/codex
```

手動の疎通確認は次で一回だけ実行する。

```bash
node tools/operations_line_codex_bridge.mjs --once
```

常時運用は、Macのログイン時にこのbridgeを起動するLaunchAgentとして登録する。
LaunchAgentの登録は、ステージングで案件作成・Slack操作・Codex起動の一連を確認した後に行う。
