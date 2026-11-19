<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { parsePasswordResetFragment, takePasswordResetLink } from '../passwordResetLink.js'

const route = useRoute()
const router = useRouter()
const link = ref(takePasswordResetLink())
const username = ref('')
const password = ref('')
const confirmation = ref('')
const minLength = ref(8)
const loading = ref(false)
const checking = ref(Boolean(link.value))
const valid = ref(false)
const sent = ref(false)
const done = ref(false)
const error = ref('')

async function checkLink() {
  if (!link.value) return
  checking.value = true
  error.value = ''
  try {
    const result = await api.validatePasswordReset(link.value)
    minLength.value = result.min_length
    valid.value = true
  } catch (e) {
    valid.value = false
    error.value = e.message || '再設定リンクを確認できませんでした。'
  } finally { checking.value = false }
}

onMounted(async () => {
  if (route.hash) await router.replace({ path: '/password-reset' })
  try { await api.csrf() } catch { /* Submission retries a stale CSRF token. */ }
  await checkLink()
})

watch(() => route.hash, async (hash) => {
  const incoming = parsePasswordResetFragment(hash)
  if (!incoming) return
  link.value = incoming
  password.value = confirmation.value = ''
  await router.replace({ path: '/password-reset' })
  await checkLink()
})

async function sendLink() {
  loading.value = true
  error.value = ''
  try {
    await api.requestPasswordReset(username.value.trim())
    sent.value = true
  } catch (e) { error.value = e.message || '送信できませんでした。時間をおいて再度お試しください。' }
  finally { loading.value = false }
}

async function changePassword() {
  error.value = ''
  if (password.value !== confirmation.value) {
    error.value = '新しいパスワードが一致しません。'
    return
  }
  loading.value = true
  try {
    await api.confirmPasswordReset({ ...link.value, new_password: password.value, new_password_confirm: confirmation.value })
    link.value = null
    password.value = confirmation.value = ''
    done.value = true
  } catch (e) { error.value = e.message || 'パスワードを変更できませんでした。' }
  finally { loading.value = false }
}

function startAgain() {
  link.value = null
  valid.value = sent.value = done.value = false
  password.value = confirmation.value = error.value = ''
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

        <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
        <div v-if="done" class="alert alert-success" role="status">
          パスワードを変更しました。新しいパスワードでログインしてください。
        </div>
        <div v-else-if="checking" role="status">リンクを確認しています…</div>
        <form v-else-if="link && valid" @submit.prevent="changePassword">
          <p class="small text-muted">{{ minLength }}文字以上の新しいパスワードを設定してください。変更後はほかの端末からログアウトされます。</p>
          <div class="mb-3">
            <label class="form-label" for="reset-password">新しいパスワード</label>
            <input id="reset-password" v-model="password" type="password" autocomplete="new-password" class="form-control" :minlength="minLength" maxlength="1024" required>
          </div>
          <div class="mb-3">
            <label class="form-label" for="reset-password-confirm">新しいパスワード（確認）</label>
            <input id="reset-password-confirm" v-model="confirmation" type="password" autocomplete="new-password" class="form-control" :minlength="minLength" maxlength="1024" required>
          </div>
          <button class="btn btn-primary w-100" :disabled="loading">{{ loading ? '変更中…' : 'パスワードを変更する' }}</button>
        </form>
        <button v-else-if="link" class="btn btn-outline-primary w-100" @click="startAgain">再設定メールを送り直す</button>
        <div v-else-if="sent">
          <div class="alert alert-info" role="status">登録済みのユーザー名であれば、再設定用メールを送信します。メールをご確認ください。</div>
          <p class="small text-muted">リンクの有効期限は30分です。届かない場合は迷惑メールフォルダと、ユーザー名をご確認ください。</p>
          <button class="btn btn-outline-secondary w-100" @click="startAgain">入力画面に戻る</button>
        </div>
        <form v-else @submit.prevent="sendLink">
          <p class="small text-muted">ユーザー名を入力すると、登録済みのメールアドレスへ再設定リンクを送信します。</p>
          <div class="mb-3">
            <label class="form-label" for="reset-username">ユーザー名</label>
            <input id="reset-username" v-model="username" type="text" autocomplete="username" maxlength="150" class="form-control" required>
          </div>
          <button class="btn btn-primary w-100" :disabled="loading">{{ loading ? '送信中…' : '再設定メールを送る' }}</button>
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
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-main);
  padding: 1rem;
  margin: 0;
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
