# SMS差し込み項目・ノート本文内画像 修正引き継ぎ

## 目的

- SMS文面へ指名・コース・オプションの内訳を差し込めるようにする。
- ノート本文の任意位置へ画像を表示できるようにする。
- 本格的なリッチテキストエディター、新規ライブラリ、migrationは追加しない。

## 変更ファイル

- `core/models.py`
- `core/services/notify.py`
- `core/views.py`
- `core/test_client_followup_updates.py`
- `frontend/src/noteContent.js`
- `frontend/src/pages/op/SettingsSmsTemplates.vue`
- `frontend/src/pages/op/CastNotes.vue`
- `frontend/src/pages/cast/CastMypage.vue`
- `frontend/src/pages/op/manualData.js`
- `docs/260823-sms-placeholders-inline-note-images.md`

## 修正内容

### SMS

以下の差し込み項目を追加した。

- `{nomination_type}`: 指名種別
- `{nomination_price}`: 指名料金
- `{course_price}`: コース料金
- `{option_names}`: 選択したオプション名
- `{option_price}`: オプション合計金額

実送信では予約へ保存された指名・コース・金額のスナップショットと、予約に紐づくオプション名を使用する。設定画面の完成文面プレビューにもサンプル値を追加した。

### ノート

- 画像アップロード後、本文のカーソル位置で「本文に挿入」を押すと `[[画像1]]` のような短い画像記号を本文へ追加する。
- 表示時は画像記号を、同じノートの検証済み `image_urls` に対応する画像へ置き換える。
- HTMLを保存・描画せず、Vueコンポーネントでテキストと画像を別要素として表示するため、任意HTMLによるXSSを持ち込まない。
- 本文へ挿入していない画像は、従来どおり本文末尾の添付画像として表示する。
- 画像を外す場合は、対応する画像記号を削除し、後続の画像番号も詰める。
- 既存ノートの本文・添付画像はそのまま表示できる。

## 実行した検証

- 関連テスト: `core.test_client_followup_updates` 7件成功
- Django全テスト: 297件成功（SQLite一時テストDB）
- `manage.py check`: 成功
- `manage.py makemigrations --check --dry-run`: `No changes detected`
- Python構文検査: 成功
- ノート画像順序・削除時番号補正のNode検査: 成功
- clean `npm ci`: 成功
- `npm audit --audit-level=high`: 0 vulnerabilities
- Vue production build: 成功
- `git diff --check`: 成功

## migration

なし。

## 残課題・手動確認事項

- 本番デプロイはこの作業では実施していない。
- デプロイ後、managerで実画像をアップロードし、「文章 → 画像 → 文章」の順番で保存・再編集できることを確認する。
- castアカウントで同じノートを開き、画像が本文途中へ表示され、タップで拡大できることを確認する。
- SMS設定画面で新しい5項目を使ったプレビューを確認する。Twilio実送信は番号・審査完了後に安全なテスト番号で別途確認する。
