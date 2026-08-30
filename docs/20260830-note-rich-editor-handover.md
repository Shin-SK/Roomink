# ノート本文リッチエディター 実装引き継ぎ

## 概要

キャスト向けノートの本文編集を、プレーンテキストと画像差し込み記号による方式から、文章と画像を同じ編集面で扱えるTiptapエディターへ変更した。

DBのカラム追加やmigrationは行っていない。既存の `CastNote.body` と `image_urls` を継続利用する。

## 変更ファイル

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/components/NoteRichEditor.vue`
- `frontend/src/noteContent.js`
- `frontend/src/pages/op/CastNotes.vue`
- `frontend/src/pages/cast/CastMypage.vue`
- `frontend/src/pages/op/manualData.js`
- `core/test_client_followup_updates.py`
- `docs/20260830-note-rich-editor-handover.md`

## 修正内容

### マネージャー側

- Tiptap 3による本文エディターを追加
- 本文、大見出し、小見出し、太字、斜体、下線、箇条書き、番号付きリスト、引用、リンクに対応
- Cloudinaryへアップロードした画像を現在のカーソル位置へ挿入
- 本文内の画像をドラッグして移動可能
- 画像を選択してDeleteキーで削除可能
- 元に戻す、やり直すに対応
- 画像上限は従来どおり1記事10枚

### キャスト側

- 保存されたリッチ本文を見出し、リスト、リンク、画像を含めて表示
- 画像タップ時の拡大表示を維持
- DOMPurifyで許可したタグ・属性だけを表示し、`v-html` によるスクリプト実行を防止

### 既存記事との互換性

- プレーンテキスト本文を段落HTMLへ自動変換
- 従来の `[[画像1]]` 形式を文章途中の画像へ自動変換
- 本文に未配置だった既存添付画像は本文末尾へ配置
- 既存記事は編集・保存するまでDB上の旧形式を変更しない

## 追加依存

- `@tiptap/vue-3`
- `@tiptap/pm`
- `@tiptap/starter-kit`
- `@tiptap/extension-image`
- `dompurify`

いずれも `frontend/package-lock.json` に固定されている。

## テスト結果

- `npm ci`: 成功
- `npm audit --audit-level=high`: 成功、脆弱性0件
- `npm run build`: 成功
- `python manage.py test core.test_client_followup_updates.ClientFollowupUpdatesTest`: 12件成功
- `python manage.py check`: 成功
- `python manage.py makemigrations --check --dry-run`: 変更なし
- `git diff --check`: 成功

ローカルの一時SQLite DBを使った実画面確認では、以下を確認した。

- 旧形式の文章・画像・文章がエディター上で正しい順に表示される
- 太字を付けて保存後、再度開いても書式が保持される
- 保存後も本文内画像が1枚保持される
- ツールバーとモーダルに目立つ表示崩れがない
- ブラウザコンソールにエラー・警告がない

## migration

なし。

## 残課題・手動確認事項

- 本番デプロイ後、実際のCloudinary画像を1枚アップロードし、文章の間への挿入・ドラッグ移動・削除・保存・キャスト側表示を実データで確認する
- スマートフォンで長い記事を編集する際の操作感は、本番または同等環境で最終確認する
- 今回は共同編集、画像リサイズ、表、文字色、動画埋め込みは対象外

## デプロイ状況

この作業ではデプロイしていない。ローカル実装・検証まで完了。
