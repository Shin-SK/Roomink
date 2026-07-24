<script setup>
import { onMounted } from 'vue'
import { api } from '../../api.js'

onMounted(async () => {
  try { await api.csrf() } catch { /* 案内表示は継続する */ }
})
</script>

<template>
  <div class="login-wrapper">
    <div class="login-card">
      <div class="login-card-body text-center">
        <img src="/logo.svg" alt="Roomink" style="height: 48px;" class="mb-4">
        <h2 class="mb-3" style="font-size: 1.25rem; font-weight: 600;">お客様アカウントのご案内</h2>
        <p class="mb-3">
          新規登録は、ご予約確定後にSMSで届く専用URLから行えます。
        </p>
        <p class="text-muted small mb-4">
          SMSが届かない場合や有効期限が切れた場合は、予約した店舗へお問い合わせください。
        </p>
        <router-link to="/cu/login" class="btn btn-primary">ログイン画面へ</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-wrapper {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-main);
  padding: 1rem;
}
.login-card {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border: 1px solid rgba(0,0,0,.125);
  border-radius: .375rem;
  box-shadow: var(--rk-shadow-lg);
}
.login-card-body { padding: 1.5rem; }
</style>
