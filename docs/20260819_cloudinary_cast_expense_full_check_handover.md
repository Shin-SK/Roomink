# Cloudinary・キャスト新規登録時雑費・フルチェック規約 引き継ぎ

## 目的

- 本番ビルドでキャスト画像をCloudinaryへアップロードできる状態にする。
- キャストの新規登録時に固定雑費も同時登録できるようにする。
- 今後の「フルチェック」で画面表示だけを確認して完了扱いにしないため、検査基準を固定する。

## 変更ファイル

- `CLAUDE.md`
- `core/serializers.py`
- `core/test_cast_create_with_expense_templates.py`
- `frontend/.env.production`
- `frontend/src/pages/op/SettingsCasts.vue`
- `docs/20260819_cloudinary_cast_expense_full_check_handover.md`

## 修正内容

### Cloudinary

- 本番フロントビルドへ公開設定 `VITE_CLOUDINARY_CLOUD_NAME` と `VITE_CLOUDINARY_UPLOAD_PRESET` を追加した。
- CloudinaryのAPI secretはフロントへ追加していない。
- 実ファイルを使い、画像選択、Cloudinaryへのアップロード、キャスト保存、一覧と編集画面への再表示まで確認した。

### キャスト新規登録時の固定雑費

- キャスト追加画面にも固定雑費欄を表示した。
- 登録前に固定雑費の追加・編集・削除ができる。
- Django側でキャストと固定雑費を同一トランザクション内に保存し、固定雑費の作成履歴も残す。
- 不正な固定雑費が含まれる場合、キャストを含めて保存しない。
- 既存キャストの固定雑費編集・有効化・無効化・履歴表示は維持した。

### フルチェック規約

- `CLAUDE.md` に、実操作、全権限、店舗分離、外部サービス、ブラウザコンソール、テストデータ整理、未確認事項の明示を必須とする規約を追加した。

## 実行結果

- 関連Djangoテスト: 12件成功（追加回帰テスト3件を含む）
- Django全テスト SQLite: 280件成功
- Django全テスト PostgreSQL 17一時DB: 280件成功
- `python3 manage.py check`: 成功
- `python3 manage.py makemigrations --check --dry-run`: 変更なし
- OpenAPI検証: 成功
- Python構文検査: 成功
- `pip check`: 成功
- `pip-audit`: 既知脆弱性0件
- `npm audit --audit-level=high`: 既知脆弱性0件
- Vue production build: 成功
- `git diff --check`: 成功
- ローカル実画面: Cloudinary実アップロード、キャスト＋固定雑費同時保存、再表示、雑費編集、履歴表示、テストキャスト削除まで成功
- ローカルブラウザコンソール: error/warning 0件

## migration

- 新規migrationは作成していない。
- 既存DBへmigrationは適用していない。検証は一時テストDBだけを使用した。

## 残課題・手動確認事項

- デプロイ後、本番のキャスト追加画面で実画像1件を使い、アップロード、保存、再表示、削除まで再確認する。
- 動作確認で作成したCloudinaryテスト画像は、Cloudinary管理画面で不要資産として削除する。
- 「オプション報酬を割合計算する」要望は本件に含めていない。全オプション共通率か、オプション別率かの仕様確定後に別件で実装する。
