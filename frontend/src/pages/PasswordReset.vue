<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const router = useRouter()
const username = ref('')
const newPassword = ref('')
const newPasswordConfirm = ref('')
const error = ref('')
const success = ref('')
const loading = ref(false)

onMounted(async () => {
  try { await api.csrf() } catch { /* ignore */ }
})

async function onSubmit() {
  error.value = ''
  success.value = ''
  if (newPassword.value.length < 4) {
    error.value = 'パスワードは4文字以上にしてください'
    return
  }
  if (newPassword.value !== newPasswordConfirm.value) {
    error.value = '新パスワードと確認用が一致しません'
    return
  }
  if (!confirm('このユーザー名のパスワードを変更します。よろしいですか？')) return
  loading.value = true
  try {
    await api.passwordReset(username.value, newPassword.value)
    success.value = 'パスワードを変更しました。ログイン画面に戻ります...'
    setTimeout(() => router.push({ name: 'login' }), 1500)
  } catch (e) {
    error.value = e.message || 'パスワード変更に失敗しました'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrapper">
    <div class="login-card">
      <div class="login-card-body">
        <div class="text-center mb-4">
          <img src="/logo.svg" alt="Roomink" style="height: 48px;">
        </div>
        <h2 class="text-center mb-4" style="font-size: 1.25rem; font-weight: 600;">パスワード再設定</h2>

        <div v-if="error" class="alert alert-danger py-2 px-3" style="font-size: 0.875rem;">
          {{ error }}
        </div>
        <div v-if="success" class="alert alert-success py-2 px-3" style="font-size: 0.875rem;">
          {{ success }}
        </div>

        <form @submit.prevent="onSubmit">
          <div class="mb-3">
            <label class="form-label">ユーザー名（電話番号）</label>
            <input
              v-model="username"
              type="text"
              class="form-control"
              autocomplete="username"
              required
            >
          </div>
          <div class="mb-3">
            <label class="form-label">新しいパスワード</label>
            <input
              v-model="newPassword"
              type="password"
              class="form-control"
              autocomplete="new-password"
              minlength="4"
              required
            >
          </div>
          <div class="mb-3">
            <label class="form-label">新しいパスワード（確認）</label>
            <input
              v-model="newPasswordConfirm"
              type="password"
              class="form-control"
              autocomplete="new-password"
              minlength="4"
              required
            >
          </div>
          <button type="submit" class="btn btn-primary btn-block w-100" :disabled="loading">
            {{ loading ? '変更中...' : 'パスワードを変更する' }}
          </button>
        </form>

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
