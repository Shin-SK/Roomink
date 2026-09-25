<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'

const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const loading = ref(false)

function homeForRole(role) {
  if (role === 'superuser') return '/platform'
  if (role === 'cast') return '/cast/mypage'
  return '/op/dashboard'
}

onMounted(async () => {
  try { await api.csrf() } catch { /* ignore */ }
  try {
    const me = await api.me()
    router.replace(route.query.next || homeForRole(me.role))
  } catch {
    // 未ログイン — そのまま表示
  }
})

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await api.login(username.value, password.value)
    resetAuthCache()
    const me = await api.me()
    router.push(route.query.next || homeForRole(me.role))
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
            <label for="login-password" class="form-label">パスワード</label>
            <div class="login-password-field">
              <input
                id="login-password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                class="form-control"
                autocomplete="current-password"
                required
              >
              <button
                type="button"
                class="login-password-toggle"
                :aria-label="showPassword ? 'パスワードを隠す' : 'パスワードを表示'"
                :aria-pressed="showPassword"
                @click="showPassword = !showPassword"
              ><i class="ti" :class="showPassword ? 'ti-eye-off' : 'ti-eye'" aria-hidden="true"></i></button>
            </div>
          </div>
          <button type="submit" class="btn btn-primary btn-block" :disabled="loading">
            {{ loading ? 'ログイン中...' : 'ログイン' }}
          </button>
        </form>

        <div class="text-center mt-3">
          <router-link :to="{ name: 'password-reset' }" class="small text-muted">
            パスワードを忘れた方はこちら
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
.login-password-field { position: relative; }
.login-password-field .form-control { padding-right: 3rem; }
.login-password-toggle {
  position: absolute;
  top: 0;
  right: 0;
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 100%;
  border: 0;
  background: transparent;
  color: #56635e;
  font-size: 1.15rem;
}
.login-password-toggle:focus-visible { outline: 2px solid #177f70; outline-offset: -3px; border-radius: 6px; }
</style>
