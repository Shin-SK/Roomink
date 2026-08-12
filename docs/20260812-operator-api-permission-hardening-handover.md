# 運営API権限強化 GPT向け引き継ぎ報告書

## 概要

本番スモークテストで確認された、castおよびcustomerが運営向けAPIのデータを参照できる問題と、staffがmanager専用設定を直接操作できる問題を修正した。

本対応は認可の強化に限定している。migration、本番データ変更、デプロイは実施していない。

## 変更ファイル

- `core/permissions.py`
  - manager専用権限を追加
  - staffは参照のみ、managerは更新可能とする権限を追加
  - ルーム一覧だけはcastのシフト申請で必要なため、castにも参照のみ許可する権限を追加
- `core/views.py`
  - 運営向けView／ViewSetへ明示的なロール権限を設定
  - マスターデータの更新をmanagerに限定
  - CTI操作をstaff／managerに限定し、対象CallLogをログインユーザーの店舗で絞り込み
- `frontend/src/router.js`
  - staffがmanager専用画面へURLを直接入力した場合、運営ダッシュボードへ戻すガードを追加
- `core/test_operator_api_permissions.py`
  - cast、customer、staff、managerおよび店舗分離の回帰テストを追加

## 権限方針

| 対象 | manager | staff | cast | customer |
| --- | --- | --- | --- | --- |
| 予約・シフト等の運営業務 | 利用可 | 利用可 | 不可 | 不可 |
| スタッフ管理 | 読み書き可 | 不可 | 不可 | 不可 |
| キャスト・コース・オプション等のマスター | 読み書き可 | 参照のみ | 不可 | 不可 |
| ルーム | 読み書き可 | 参照のみ | 参照のみ | 不可 |
| 売上・精算・CSV・LINE／電話設定 | 利用可 | 不可 | 不可 | 不可 |
| CTI操作 | 利用可（自店舗のみ） | 利用可（自店舗のみ） | 不可 | 不可 |

castによるルーム参照は、既存のシフト申請画面を維持するため意図的に残している。更新はmanagerだけが可能。

## 修正内容

- cast/customerから顧客、スタッフ、予約、シフト、売上、設定等の運営APIへアクセスした場合は403を返す。
- cast/customerから運営APIのPOST／PUT／PATCH／DELETEを実行できない。
- staffはスタッフアカウントの一覧取得・作成およびmanager専用マスターの変更を実行できない。
- managerは従来どおりスタッフ管理と各種設定を行える。
- staffの予約・スケジュール等の通常業務と、castの自分向け画面・シフト申請用ルーム参照は維持した。
- CTIの開始・完了・メモ更新は、自店舗のCallLogだけを操作できる。他店舗IDは404となり、情報の存在も漏らさない。
- フロント側でもstaffのmanager専用画面への直接遷移を防止した。API側の認可も独立して実施しているため、フロント制御の回避だけでは操作できない。

## テスト結果

### 関連テスト

- `python3 manage.py test core.test_operator_api_permissions`
- 6件成功

確認内容：

- cast/customerによる運営API参照拒否
- cast/customerによる運営データ変更拒否
- staffによるスタッフ管理・マスター変更拒否
- staff/managerの正規業務維持
- castのシフト申請用ルーム参照維持
- CTIの店舗分離

### Django全テスト

- SQLite: 252件成功
- PostgreSQL 17の一時テストDB: 252件成功
- PostgreSQL検証は新規の一時Dockerコンテナだけを使用し、既存ローカルDBおよび本番DBには触れていない。

### その他

- `python3 manage.py check`: 成功、問題なし
- `python3 manage.py makemigrations --check --dry-run`: 成功、変更なし
- Python構文検査: 成功
- Vue production build: 成功
- `git diff --check`: 成功

## migration

- migrationの追加なし
- migration適用なし
- DBスキーマ変更なし

## 本番反映前後の手動確認事項

1. managerでログインし、スタッフ管理、設定、売上、予約の通常操作ができること。
2. staffでログインし、予約・スケジュール等の通常業務ができること。
3. staffでmanager専用URLへ直接アクセスすると運営ダッシュボードへ戻ること。
4. castでログインし、自分の画面とシフト申請が利用できること。
5. castのセッションで `/api/customers/`、`/api/staffs/`、`/api/orders/` 等が403になること。
6. customerでログインし、顧客マイページが利用でき、運営APIは403になること。
7. CTIの通常操作をstaff/managerで確認し、他店舗データが表示・更新されないこと。

## 残課題

- 本変更はまだ本番未反映。コミット、push、デプロイ後に権限別の本番スモークテストが必要。
- ブラウザ上の画面非表示だけに依存せずAPI認可をテストしているが、今後運営APIを追加する際も同じ権限テストを追加すること。
- Sentry、Twilio審査、正式データ入力等は本件の変更対象外。
