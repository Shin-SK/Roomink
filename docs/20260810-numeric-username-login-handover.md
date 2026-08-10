# GPT引き継ぎ報告書：数字ユーザー名ログインの分離修正

## 最終判定

`PR READY / CI GREEN`

## 原因

運営・キャスト共通API `/api/auth/login/` が、数字を1文字でも含む入力を電話番号として正規化していた。これにより `manager2`、`cast01`、`819012345678` のような正規のDjango usernameが別文字列へ変換され、認証に失敗していた。

## 変更ファイル

- `core/views.py`
- `core/test_numeric_username_login.py`
- `frontend/src/pages/op/manualData.js`
- `docs/20260810-current-status-and-remaining-work-handover.md`
- `docs/20260810-numeric-username-login-handover.md`

## 修正前後の認証判定

### 修正前

- `/api/auth/login/`: 数字を含む入力を電話番号正規化してからusername認証
- `/api/cu/login/`: Customer電話番号を正規化し、紐づくUserを一意に特定して認証

### 修正後

- `/api/auth/login/`: 入力の見た目にかかわらず、常にDjango usernameとして認証
- `/api/cu/login/`: 従来どおりCustomer電話番号だけを正規化して認証
- 同じ文字列がstaff usernameとCustomer電話番号に存在しても、呼び出したAPIの文脈で別々に認証
- 認証成功後のroleは既存のUserProfile／Customer紐づけから決定

## セキュリティ・権限回帰

- 顧客電話番号の候補が0件または複数Userの場合は同じ401応答で拒否
- 誤パスワードと未登録電話番号は同じ401応答
- 顧客ログインからusername認証へのfallbackなし
- staffは顧客API権限を取得せず、customerはoperator APIへ入れない
- castはmanager専用売上APIへ入れない
- ログアウトはCSRFなしで403、正しいCSRF付きで成功
- パスワード・完全な電話番号をログへ追加していない

## 新規テスト

`core.test_numeric_username_login` に9件追加した。

- 数字のみstaff username
- 電話番号形式のmanager username
- `81`始まりの数字usernameを電話番号へ書き換えないこと
- 数字を含むmanager／cast username回帰
- staff usernameとCustomer電話番号が同一文字列の競合
- 顧客ログインの列挙防止
- 複数Customer User候補の拒否
- role／permission境界
- logout／CSRF

## ローカル検証結果

- 関連テスト: 9件成功
- Django全テスト SQLite: 183件成功
- `manage.py check`: 成功
- `makemigrations --check --dry-run`: `No changes detected`
- OpenAPI validation: 成功
- Python構文検査: 成功
- `pip check`: 成功
- `pip-audit`: 既知脆弱性0件
- clean `npm ci`: 成功
- `npm audit --audit-level=high`: 0件
- Vue production build: 成功
- migration: なし

## GitHub／CI

- branch: `fix/numeric-staff-login`
- commit: PR #22のHead SHAを正とする（最終報告に記載）
- PR: `#22`
- Backend checks: 成功
- Django全テスト SQLite: 183件成功
- Django全テスト PostgreSQL 17: 183件成功
- Frontend checks: 成功
- Netlify Deploy Preview: 成功

## 残課題

- `main`のbranch protectionは、管理権限を持つ`Shin-SK`でGitHubへ再認証後に設定する。
- 次の推奨作業は、予約の連絡者／実利用者分離。
