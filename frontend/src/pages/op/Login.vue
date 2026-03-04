<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'

const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

onMounted(async () => {
  // 1. csrftoken cookieを確実に発行させる
  // 2. 既にログイン済みならdashboardへ飛ばす
  try {
    await api.me()
    router.replace('/op/dashboard')
  } catch {
    // 未ログイン — そのまま表示（csrftoken cookieはレスポンスで発行済み）
  }
})

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await api.login(username.value, password.value)
    resetAuthCache()
    router.push('/op/dashboard')
  } catch (e) {
    error.value = e.message || 'ログインに失敗しました'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrapper">
    <div class="login-card card">
      <div class="card-body">
        <div class="text-center mb-4">
          <img src="/logo.svg" alt="Roomink" style="height: 48px;">
        </div>
        <h2 class="text-center mb-4" style="font-size: 1.25rem; font-weight: 600;">運営ログイン</h2>

        <div v-if="error" class="alert alert-danger py-2 px-3" style="font-size: 0.875rem;">
          {{ error }}
        </div>

        <form @submit.prevent="onSubmit">
          <div class="mb-3">
            <label class="form-label">ユーザー名</label>
            <input
              v-model="username"
              type="text"
              class="form-control"
              autocomplete="username"
              required
            >
          </div>
          <div class="mb-3">
            <label class="form-label">パスワード</label>
            <input
              v-model="password"
              type="password"
              class="form-control"
              autocomplete="current-password"
              required
            >
          </div>
          <button type="submit" class="btn btn-primary btn-block" :disabled="loading">
            {{ loading ? 'ログイン中...' : 'ログイン' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-main);
  padding: 1rem;
}
.login-card {
  width: 100%;
  max-width: 400px;
  box-shadow: var(--rk-shadow-lg);
}
</style>
