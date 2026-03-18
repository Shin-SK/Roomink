<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'

const router = useRouter()
const stores = ref([])
const form = ref({ store_id: '', phone: '', password: '', display_name: '' })
const error = ref('')
const loading = ref(false)
const storesLoading = ref(true)

onMounted(async () => {
  try { await api.csrf() } catch { /* ignore */ }
  try {
    const data = await api.getStoreListPublic()
    stores.value = data.stores
    if (stores.value.length === 1) {
      form.value.store_id = stores.value[0].store_id
    }
  } catch {
    // 未ログインでも店舗一覧は取得可能
  } finally {
    storesLoading.value = false
  }
})

async function onSubmit() {
  error.value = ''
  if (!form.value.store_id) {
    error.value = '店舗を選択してください'
    return
  }
  if (!form.value.phone || !form.value.password) {
    error.value = '電話番号とパスワードは必須です'
    return
  }

  loading.value = true
  try {
    await api.customerSignup(
      form.value.phone,
      form.value.password,
      form.value.display_name,
      form.value.store_id,
    )
    // 登録後に自動ログイン
    resetAuthCache()
    await api.login(form.value.phone, form.value.password)
    resetAuthCache()
    router.push('/cu/mypage')
  } catch (e) {
    error.value = e.message || '登録に失敗しました'
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
        <h2 class="text-center mb-4" style="font-size: 1.25rem; font-weight: 600;">新規登録</h2>

        <div v-if="error" class="alert alert-danger py-2 px-3" style="font-size: 0.875rem;">
          {{ error }}
        </div>

        <div v-if="storesLoading" class="text-center py-3">
          <div class="spinner-border spinner-border-sm text-primary"></div>
        </div>

        <form v-else @submit.prevent="onSubmit">
          <!-- 店舗選択 -->
          <div class="mb-3">
            <label class="form-label">店舗 <span class="text-danger">*</span></label>
            <select v-model="form.store_id" class="form-select" required>
              <option value="">選択してください</option>
              <option v-for="s in stores" :key="s.store_id" :value="s.store_id">{{ s.store_name }}</option>
            </select>
          </div>

          <div class="mb-3">
            <label class="form-label">お名前</label>
            <input
              v-model="form.display_name"
              type="text"
              class="form-control"
              placeholder="表示名（任意）"
            >
          </div>

          <div class="mb-3">
            <label class="form-label">電話番号 <span class="text-danger">*</span></label>
            <input
              v-model="form.phone"
              type="tel"
              class="form-control"
              placeholder="090-1234-5678"
              autocomplete="username"
              required
            >
          </div>

          <div class="mb-3">
            <label class="form-label">パスワード <span class="text-danger">*</span></label>
            <input
              v-model="form.password"
              type="password"
              class="form-control"
              autocomplete="new-password"
              required
            >
          </div>

          <button type="submit" class="btn btn-primary btn-block" :disabled="loading">
            {{ loading ? '登録中...' : '登録する' }}
          </button>
        </form>

        <div class="text-center mt-3">
          <router-link to="/cu/login" class="small">すでにアカウントをお持ちの方</router-link>
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
