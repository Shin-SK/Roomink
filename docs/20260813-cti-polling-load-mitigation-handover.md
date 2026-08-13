# CTIポーリング負荷軽減 引き継ぎ報告

## 対象

本番スモークテスト中に断続的に発生したHeroku H12（30秒タイムアウト）への初期負荷軽減。

## 変更ファイル

- `frontend/src/components/CtiIncomingPanel.vue`
- `docs/20260813-cti-polling-load-mitigation-handover.md`

## 修正内容

- オペレーター画面表示中のCTI着信確認間隔を2秒から5秒へ変更。
- ブラウザーのタブが非表示の場合の確認間隔を10秒から30秒へ変更。
- 着信パネルの手動操作、画面復帰時の即時確認、401/403時の停止処理は維持。

複数のオペレーター画面やスモークテスト画面を同時に開いた際、着信がない状態でもCTIキューAPIへ継続して発生していたリクエスト数を抑えるための最小変更である。

## 検証

- `npm ci`：成功
- `npm audit --audit-level=high`：脆弱性0件
- Vue production build：成功（476 modules transformed）
- Django全テスト：253件成功（SQLite一時テストDB）
- `python3 manage.py check`：問題なし
- `python3 manage.py makemigrations --check --dry-run`：変更なし
- Python構文検査：成功
- `git diff --check`：問題なし

リポジトリ内の既存`venv`はPython実体へのリンクが切れていたため、Python 3.12の一時仮想環境へ`requirements.txt`を導入して検証した。既存ローカルDBと本番DBは変更していない。

## 本番反映後の確認

- オペレーター画面で着信パネルが表示されること。
- 画面表示中は約5秒間隔でCTIキューAPIが呼ばれること。
- 非表示タブでは約30秒間隔まで低下すること。
- 画面へ戻った際に即時確認されること。
- HerokuログでH12が再発しないか確認すること。

## 残課題

- この変更はH12への初期軽減であり、根本原因の完全な解消を保証するものではない。本番反映後も継続監視し、再発時は遅いAPIまたはDB処理をリクエスト単位で特定する。
- EcoからBasicへの変更だけでは公表スペック上のCPU・メモリ増加はない。再発時の増強はStandard系または複数dynoを、費用と実利用負荷を確認して判断する。
- 仮電話番号は今回変更しない。Twilioの音声・SMS番号が確定した後、環境変数と表示データを正式番号へ差し替え、発着信・SMSの最終試験を行う。
