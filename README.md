# Roomink

Django REST FrameworkとVue 3（Vite）で構成された業務Webアプリケーションです。

## 開発・CI環境

- Python: 3.12系（`.python-version`）
- Django: 5.2系（`requirements.txt`）
- Node.js: 22系（Vite 7の要件を満たすこと）
- PostgreSQL: 17系（CI・Heroku本番）。ローカルではSQLiteも利用可能

## 主な確認コマンド

Backend（SQLite）:

```bash
python3 manage.py check
python3 manage.py makemigrations --check --dry-run
python3 manage.py spectacular --validate --fail-on-warn --file /tmp/roomink-schema.yml
python3 manage.py test core
```

Backend（PostgreSQL）では、テスト専用DBを用意したうえで`USE_POSTGRES=1`と
`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_HOST`、
`POSTGRES_PORT`を設定し、同じテストコマンドを実行します。本番DBをテストへ使用しないでください。

Frontend:

```bash
cd frontend
npm ci
npm audit --audit-level=high
npm run build
```

## GitHub Actions

Pull Requestと`main`へのpushで、BackendとFrontendを分けて次を検査します。

- Django system check、migration作成漏れ、OpenAPI、Python構文
- Django全テスト（SQLite / PostgreSQL 17）
- Python依存整合性と既知脆弱性
- `npm ci`、High以上の既知脆弱性、Vue production build

CIではTwilio、LINE、CTIの資格情報を使用せず、外部サービスへの実送信と本番DB接続を行いません。
現在のHeroku・Netlifyは`main`統合後に自動デプロイされる構成です。branch protectionは、
GitHub上でCIが安定して成功することを確認してから有効化してください。
