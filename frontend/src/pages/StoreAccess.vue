<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api.js'
import { openStore } from '../storeSelection.js'
import LayoutOperator from '../components/LayoutOperator.vue'

const data = ref({ memberships: [], invitations: [] })
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const activeStoreId = ref('')
const user = ref(null)
const roleLabel = role => role === 'manager' ? 'マネージャー' : 'スタッフ'
const activeStore = computed(() => data.value.memberships.find(member => String(member.store_id) === String(activeStoreId.value)))
const hasOperatorLayout = computed(() => ['manager', 'staff'].includes(user.value?.role))
const pageLayout = computed(() => hasOperatorLayout.value ? LayoutOperator : 'div')

async function load() {
  error.value = ''
  try {
    const [access, accountUser] = await Promise.all([api.getStoreAccess(), api.me()])
    data.value = access
    activeStoreId.value = accountUser.store_id || ''
    user.value = accountUser
  }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function respond(invite, action) {
  if (!window.confirm(action === 'accept'
    ? `「${invite.store_name}」へ${roleLabel(invite.role)}として参加しますか？`
    : `「${invite.store_name}」からの招待を辞退しますか？`)) return
  busy.value = true
  error.value = ''
  try {
    await api.respondStoreInvitation(invite.id, action)
    await load()
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}

async function logout() {
  try { await api.logout(); window.location.assign('/login') }
  catch (e) { error.value = e.message }
}

function switchStore(storeId) {
  if (String(storeId) === String(activeStoreId.value)) return
  openStore(storeId)
}
onMounted(load)
</script>

<template>
  <component :is="pageLayout">
  <main class="store-access">
    <div class="store-access__heading">
      <h1>店舗・招待</h1>
      <button v-if="!hasOperatorLayout" class="btn btn-outline-secondary btn-sm" @click="logout">ログアウト</button>
    </div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <p v-if="loading">読み込み中...</p>
    <template v-else>
      <section v-if="activeStore" class="store-active mb-3">
        <span>操作中の店舗</span>
        <strong>{{ activeStore.store_name }}</strong>
        <small>{{ roleLabel(activeStore.role) }}</small>
      </section>
      <section class="card mb-3">
        <div class="card-body">
          <h2 class="h5">店舗を切り替える</h2>
          <p v-if="!data.memberships.length" class="text-muted mb-0">現在、利用できる店舗はありません。店舗の管理者に招待を依頼してください。</p>
          <div v-for="member in data.memberships" :key="member.store_id" class="store-membership">
            <div class="text-break" style="min-width: 0"><strong>{{ member.store_name }}</strong><div class="small text-muted">{{ roleLabel(member.role) }}</div></div>
            <span v-if="String(member.store_id) === String(activeStoreId)" class="store-membership__active">操作中</span>
            <button v-else class="btn btn-outline-primary btn-sm" @click="switchStore(member.store_id)">切り替える</button>
          </div>
        </div>
      </section>
      <section class="card">
        <div class="card-body">
          <h2 class="h5">届いている招待</h2>
          <p v-if="!data.invitations.length" class="text-muted mb-0">承認待ちの招待はありません。</p>
          <article v-for="invite in data.invitations" :key="invite.id" class="py-3 border-bottom text-break">
            <h3 class="h6">{{ invite.store_name }}</h3>
            <p class="small mb-2">招待者：{{ invite.invited_by_name }} ／ 権限：{{ roleLabel(invite.role) }}<br>
              有効期限：{{ new Date(invite.expires_at).toLocaleString('ja-JP') }}</p>
            <div class="d-flex gap-2">
              <button class="btn btn-primary btn-sm" :disabled="busy" @click="respond(invite, 'accept')">承認して参加</button>
              <button class="btn btn-outline-secondary btn-sm" :disabled="busy" @click="respond(invite, 'decline')">辞退</button>
            </div>
          </article>
        </div>
      </section>
    </template>
  </main>
  </component>
</template>

<style scoped>
.store-access { max-width: 760px; margin: 0 auto; padding: 1.25rem 0 2rem; }

.store-access__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.store-access__heading h1 { margin: 0; font-size: 1.25rem; }

.store-active {
  display: grid;
  gap: 0.15rem;
  padding: 0.85rem 1rem;
  border: 1px solid rgba(var(--bs-primary-rgb), 0.25);
  border-radius: 10px;
  background: rgba(var(--bs-primary-rgb), 0.05);
}

.store-active span,
.store-active small { color: var(--bs-secondary-color); font-size: 0.78rem; }
.store-active strong { font-size: 1rem; }

.store-membership {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.7rem 0;
  border-bottom: 1px solid var(--bs-border-color);
}

.store-membership:last-child { border-bottom: 0; padding-bottom: 0; }

.store-membership__active {
  flex: 0 0 auto;
  color: var(--bs-primary);
  font-size: 0.78rem;
  font-weight: 600;
}
</style>
