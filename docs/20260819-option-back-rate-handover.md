# オプションバック率対応 引き継ぎ報告

## 概要

キャストごとに、オプション売上のバック率を0〜100%で設定できるようにした。
従来の「オプション全額バック」は100%としてデータ移行し、旧API形式も引き続き受け付ける。

## 変更ファイル

- `core/models.py`
  - `Cast.option_back_rate`（0〜100%）を追加
- `core/migrations/0059_cast_option_back_rate.py`
  - 新フィールドを追加
  - `option_fullback_enabled=True` の既存キャストを100%へ移行
- `core/serializers.py`
  - 新しい％指定と旧全額バック指定を相互同期
- `core/views.py`
  - キャスト給与見込み、日次精算、日次精算CSVを％計算へ変更
- `core/services/sales.py`
  - 売上ダッシュボードとCSVを％計算へ変更
- `core/admin.py`
  - 管理画面では新しい％項目だけを編集対象に変更
- `frontend/src/pages/op/SettingsCasts.vue`
  - オプションバック率入力（0〜100%）を追加
- `frontend/src/pages/op/SalesSummary.vue`
  - コースとオプションのバック率を表示
- `frontend/src/pages/op/DailySettlement.vue`
  - 日次精算にオプションバック率を表示
- `core/test_option_back_rate.py`
  - 0%・40%・100%、端数切り捨て、旧API互換の回帰テストを追加

## 計算仕様

- コースバック：`floor(コース売上 × コースバック率 / 100)`
- オプションバック：`floor(オプション売上 × オプションバック率 / 100)`
- 給与見込み：コースバック + オプションバック
- 100%は従来の「全額バック」と同じ
- 端数は既存のコースバックと同じく切り捨て

## テスト結果

- 関連テスト：4件成功
- `manage.py check`：成功
- `makemigrations --check --dry-run`：差分なし
- Python構文検査：成功
- Vue production build：成功
- Django全テスト：257件すべて成功
- 最新`main`への載せ替え時、固定日付テストは`main`側ですでに安定化済みだったため追加変更なし

## migration

- 新規migration：`0059_cast_option_back_rate`
- 既存の全額バック利用者は100%へ自動変換される
- 本番反映時は通常のrelease phaseで適用する

## 残課題・手動確認

- デプロイ後、キャスト設定で0%・任意％・100%を保存できることを確認する
- 日次精算と売上集計で同じバック額が表示されることを確認する
- 本番データへのmigration適用および本番デプロイは、この作業時点では未実施
