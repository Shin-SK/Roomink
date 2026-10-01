# Roomink ステージング運用

## 目的

本番運用中の店舗へ影響を出さず、修正を実機相当の環境で確認してから本番へ反映する。

## 環境の分離

- 本番とステージングで、Web URL・API・PostgreSQLを完全に分ける。
- 本番の顧客、電話番号、認証情報、通話・SMS・LINE設定はコピーしない。
- ステージングのSMSは常にダミー送信とする。
- 公開予約の認証コードはステージング専用の固定値を環境変数で設定できる。
- 画面上部へ常時 `STAGING` を表示する。
- デモ店舗はフラッグシップの画面構成に近づけるが、人物・電話番号・住所・予約はすべて架空データを使う。

## リリース手順

1. 機能ブランチで修正する。
2. 自動テストとビルドを完了する。
3. `staging` ブランチへ反映する。
4. ステージングのバックエンド・フロントエンドへデプロイする。
5. `seed_staging_demo --reset` で匿名化済みデータを更新する。
6. ステージングで対象機能と既存主要動線を確認する。
7. 合格した同じコミットを `main` へ反映する。
8. 本番の自動テスト・デプロイ・ヘルスチェックを確認する。

## 必須の安全設定

バックエンドには最低限、次を設定する。

```text
DJANGO_ENV=staging
SMS_DUMMY_MODE=1
FRONTEND_URL=<ステージングWeb URL>
RESERVATION_LINK_BASE_URL=<ステージングWeb URL>
DJANGO_ALLOWED_HOSTS=<ステージングAPIホスト>
DJANGO_CORS_ALLOWED_ORIGINS=<ステージングWeb URL>
DJANGO_CSRF_TRUSTED_ORIGINS=<ステージングWeb URL>
PUBLIC_BOOKING_TEST_CODE=<6桁の検証コード>
DJANGO_EMAIL_BACKEND=django.core.mail.backends.dummy.EmailBackend
```

本番のTwilio、LINE、SIP、Slack、メール送信用認証情報は設定しない。

## デモデータ

```bash
python3 manage.py seed_staging_demo --reset
```

実行時は `STAGING_MANAGER_PASSWORD` と `STAGING_CAST_PASSWORD` が必要。パスワードはリポジトリ、Notion、ログへ記録しない。

## 本番反映の条件

- CIがすべて合格している。
- ステージングの対象機能をブラウザで確認している。
- SMS・電話・メール・LINEが本番へ誤送信されないことを確認している。
- DB変更がある場合、ステージングでマイグレーション済みである。
- 本番反映後の確認項目と切り戻し方法が決まっている。
