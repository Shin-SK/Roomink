<template>
  <div class="login-wrapper">
    <div class="login-card">
      <div class="login-card-body">
        <div class="text-center mb-4">
          <img src="/logo.svg" alt="Roomink" style="height: 48px;">
        </div>
        <h2 class="text-center mb-4" style="font-size: 1.25rem; font-weight: 600;">パスワード再設定</h2>

        <div class="alert alert-info py-3 px-3" style="font-size: 0.875rem;">
          パスワード再設定は現在利用できません。<br>
          パスワードを忘れた場合は、管理者へお問い合わせください。
        </div>

        <div class="text-center mt-3">
          <router-link :to="{ name: 'login' }" class="small text-muted">
            ログイン画面に戻る
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-wrapper {
  height: 100dvh;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-main);
  padding: 0 1rem;
  margin: 0;
  overflow: hidden;
}
.login-card {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border: 1px solid rgba(0,0,0,.125);
  border-radius: .375rem;
  box-shadow: var(--rk-shadow-lg);
}
.login-card-body {
  padding: 1rem;
}
</style>
