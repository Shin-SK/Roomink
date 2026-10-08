<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api.js'
import LayoutOperator from '../components/LayoutOperator.vue'
import LayoutCast from '../components/LayoutCast.vue'
import LayoutCustomer from '../components/LayoutCustomer.vue'

const user = ref(null)
const loading = ref(true)
const saving = ref(false)
const currentPassword = ref('')
const newPassword = ref('')
const newPasswordConfirm = ref('')
const showPasswords = ref(false)
const error = ref('')
const success = ref('')

const layoutComponent = computed(() => {
  if (user.value?.role === 'cast') return LayoutCast
  if ((user.value?.roles || []).includes('customer') && user.value?.role === 'customer') return LayoutCustomer
  return LayoutOperator
})

const minimumLength = computed(() => Number(user.value?.password_policy?.min_length) || 8)

function errorText(exc) {
  const data = exc?.data
  if (data && typeof data === 'object') {
    const messages = Object.values(data).flat().filter(Boolean)
    if (messages.length) return messages.join('\n')
  }
  return exc?.message || 'パスワードを変更できませんでした。'
}

async function submit() {
  error.value = ''
  success.value = ''
  if (newPassword.value !== newPasswordConfirm.value) {
    error.value = '新しいパスワードが一致しません。'
    return
  }
  saving.value = true
  try {
    const data = await api.changePassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
      new_password_confirm: newPasswordConfirm.value,
    })
    currentPassword.value = ''
    newPassword.value = ''
    newPasswordConfirm.value = ''
    success.value = data.detail || 'パスワードを変更しました。'
  } catch (exc) {
    error.value = errorText(exc)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    user.value = await api.me()
  } catch (exc) {
    error.value = errorText(exc)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-if="loading" class="account-security-loading">
    <div class="spinner-border text-primary"></div>
  </div>
  <component :is="layoutComponent" v-else-if="user">
    <div class="account-security-page">
      <div class="account-security-heading">
        <div>
          <h2>ログインと安全</h2>
          <p>現在のパスワードを確認して、新しいパスワードへ変更できます。</p>
        </div>
        <span class="account-security-shield"><i class="ti ti-shield-lock"></i></span>
      </div>

      <div v-if="success" class="alert alert-success" role="status">{{ success }}</div>
      <div v-if="error" class="alert alert-danger" role="alert" style="white-space: pre-line;">{{ error }}</div>

      <form class="card account-security-card" @submit.prevent="submit">
        <div class="card-body">
          <div class="mb-3">
            <label for="current-password" class="form-label">現在のパスワード</label>
            <input
              id="current-password"
              v-model="currentPassword"
              :type="showPasswords ? 'text' : 'password'"
              class="form-control"
              autocomplete="current-password"
              required
            >
          </div>
          <div class="mb-3">
            <label for="new-password" class="form-label">新しいパスワード</label>
            <input
              id="new-password"
              v-model="newPassword"
              :type="showPasswords ? 'text' : 'password'"
              class="form-control"
              autocomplete="new-password"
              :minlength="minimumLength"
              required
            >
            <div class="form-text">
              {{ minimumLength }}文字以上。大文字や記号を無理に入れる必要はありません。
            </div>
          </div>
          <div class="mb-3">
            <label for="new-password-confirm" class="form-label">新しいパスワード（確認）</label>
            <input
              id="new-password-confirm"
              v-model="newPasswordConfirm"
              :type="showPasswords ? 'text' : 'password'"
              class="form-control"
              autocomplete="new-password"
              :minlength="minimumLength"
              required
            >
          </div>
          <label class="account-security-show">
            <input v-model="showPasswords" type="checkbox">
            入力したパスワードを表示する
          </label>
          <div class="account-security-note">
            <i class="ti ti-info-circle"></i>
            変更すると、この端末以外のログインは順次終了します。
          </div>
          <button type="submit" class="btn btn-primary w-100" :disabled="saving">
            {{ saving ? '変更中...' : 'パスワードを変更する' }}
          </button>
        </div>
      </form>
    </div>
  </component>
  <div v-else class="alert alert-danger">{{ error }}</div>
</template>

<style scoped>
.account-security-loading { min-height: 60vh; display: grid; place-items: center; }
.account-security-page { max-width: 620px; margin: 0 auto; }
.account-security-heading { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1rem; }
.account-security-heading h2 { margin: 0 0 .25rem; font-size: 1.35rem; }
.account-security-heading p { margin: 0; color: #64748b; font-size: .9rem; }
.account-security-shield { width: 48px; height: 48px; display: grid; place-items: center; border-radius: 50%; color: #177f70; background: #eaf7f4; flex: 0 0 auto; }
.account-security-shield i { font-size: 25px; }
.account-security-card { border: 1px solid #dbe6e3; box-shadow: 0 8px 24px rgb(15 23 42 / 6%); }
.account-security-card .card-body { padding: 1.25rem; }
.account-security-show { display: flex; align-items: center; gap: .5rem; margin-bottom: 1rem; color: #475569; font-size: .9rem; }
.account-security-note { display: flex; gap: .5rem; margin-bottom: 1rem; padding: .75rem; border-radius: 8px; color: #475569; background: #f8faf9; font-size: .85rem; }
@media (max-width: 575px) {
  .account-security-heading { align-items: flex-start; }
  .account-security-card .card-body { padding: 1rem; }
}
</style>
