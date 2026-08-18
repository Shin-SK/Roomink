<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'
import { customerPath, routeStoreSlug } from '../../customerStore.js'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const maskedPhone = ref('')
const password = ref('')
const passwordConfirm = ref('')
const token = ref('')
const storeSlug = routeStoreSlug(route)

onMounted(async () => {
  try {
    token.value = typeof route.query.token === 'string' ? route.query.token : ''
    if (token.value) window.history.replaceState({}, '', customerPath(route, 'activate'))
    await api.csrf()
    const data = await api.getCustomerActivation(token.value, storeSlug)
    maskedPhone.value = data.masked_phone
  } catch (e) {
    error.value = e.message || 'この案内は利用できません。店舗へお問い合わせください。'
  } finally {
    loading.value = false
  }
})

async function activate() {
  error.value = ''
  if (password.value !== passwordConfirm.value) {
    error.value = 'パスワードが一致しません。'
    return
  }
  submitting.value = true
  try {
    const data = await api.activateCustomer(token.value, password.value, passwordConfirm.value)
    resetAuthCache()
    router.replace(data.next || customerPath(route, 'mypage'))
  } catch (e) {
    error.value = Array.isArray(e.data?.detail) ? e.data.detail.join('\n') : (e.message || '設定できませんでした。')
  } finally {
    submitting.value = false
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
        <h2 class="text-center mb-3" style="font-size: 1.25rem; font-weight: 600;">初回パスワード設定</h2>

        <div v-if="loading" class="text-center py-4">
          <div class="spinner-border text-primary"></div>
        </div>
        <template v-else>
          <div v-if="error" class="alert alert-danger" style="white-space: pre-line;">{{ error }}</div>
          <form v-if="maskedPhone" @submit.prevent="activate">
            <div class="mb-3">
              <label class="form-label">登録電話番号</label>
              <input :value="maskedPhone" class="form-control" disabled>
            </div>
            <div class="mb-3">
              <label class="form-label">パスワード</label>
              <input v-model="password" type="password" class="form-control" autocomplete="new-password" required>
              <small class="text-muted">8文字以上で、推測されにくいものを設定してください。</small>
            </div>
            <div class="mb-4">
              <label class="form-label">パスワード（確認）</label>
              <input v-model="passwordConfirm" type="password" class="form-control" autocomplete="new-password" required>
            </div>
            <button class="btn btn-primary w-100" :disabled="submitting">
              {{ submitting ? '設定中...' : 'パスワードを設定する' }}
            </button>
          </form>
          <div v-else class="text-center mt-3">
            <router-link :to="customerPath(route, 'signup')" class="btn btn-outline-primary">案内を見る</router-link>
          </div>
        </template>
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
