<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'

const router = useRouter()
const route = useRoute()
const phone = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

onMounted(async () => {
  try { await api.csrf() } catch { /* ignore */ }
  try {
    await api.me()
    router.replace(route.query.next || '/cu/mypage')
  } catch {
    // 未ログイン
  }
})

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await api.login(phone.value, password.value)
    resetAuthCache()
    router.push(route.query.next || '/cu/mypage')
  } catch (e) {
    error.value = e.message || 'ログインに失敗しました'
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
        <h2 class="text-center mb-4" style="font-size: 1.25rem; font-weight: 600;">ログイン</h2>

        <div v-if="error" class="alert alert-danger py-2 px-3" style="font-size: 0.875rem;">
          {{ error }}
        </div>

        <form @submit.prevent="onSubmit">
          <div class="mb-3">
            <label class="form-label">電話番号</label>
            <input
              v-model="phone"
              type="tel"
              class="form-control"
              autocomplete="username"
              placeholder="090-1234-5678"
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

        <div class="text-center mt-3">
          <router-link to="/cu/signup" class="small">アカウントをお持ちでない方はこちら</router-link>
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
