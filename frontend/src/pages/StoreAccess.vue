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
const hasOperatorLayout = computed(() => Boolean(user.value?.id))
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
      <div>
        <p class="store-access__eyebrow">ROOMINK ACCOUNT</p>
        <h1>店舗を切り替える</h1>
        <p>操作する店舗と、届いている招待を管理できます。</p>
      </div>
      <button v-if="!hasOperatorLayout" class="btn btn-outline-secondary btn-sm" @click="logout">ログアウト</button>
    </div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <p v-if="loading">読み込み中...</p>
    <template v-else>
      <section v-if="activeStore" class="store-active">
        <span class="store-active__icon"><i class="ti ti-building-store"></i></span>
        <div>
          <span>現在操作中</span>
          <strong>{{ activeStore.store_name }}</strong>
          <small>{{ roleLabel(activeStore.role) }}</small>
        </div>
      </section>
      <section class="store-section">
        <div class="store-section__head">
          <div>
            <h2>利用できる店舗</h2>
            <p>切り替えると、その店舗の管理画面が開きます。</p>
          </div>
        </div>
        <div class="store-section__body">
          <p v-if="!data.memberships.length" class="text-muted mb-0">現在、利用できる店舗はありません。店舗の管理者に招待を依頼してください。</p>
          <div v-for="member in data.memberships" :key="member.store_id" class="store-membership">
            <span class="store-membership__icon"><i class="ti ti-building-store"></i></span>
            <div class="store-membership__copy"><strong>{{ member.store_name }}</strong><span>{{ roleLabel(member.role) }}</span></div>
            <span v-if="String(member.store_id) === String(activeStoreId)" class="store-membership__active"><i class="ti ti-check"></i> 操作中</span>
            <button v-else class="btn btn-outline-primary btn-sm" @click="switchStore(member.store_id)">切り替える <i class="ti ti-arrow-right"></i></button>
          </div>
        </div>
      </section>
      <section class="store-section">
        <div class="store-section__head">
          <div>
            <h2>届いている招待</h2>
            <p>承認すると、対象店舗の管理画面を利用できます。</p>
          </div>
        </div>
        <div class="store-section__body">
          <p v-if="!data.invitations.length" class="text-muted mb-0">承認待ちの招待はありません。</p>
          <article v-for="invite in data.invitations" :key="invite.id" class="store-invitation text-break">
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
.store-access { max-width: 860px; margin: 0 auto; padding: 1.75rem 0 3rem; }

.store-access__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.store-access__eyebrow { margin: 0 0 .25rem; color: #2a9d8f; font-size: .72rem; font-weight: 800; letter-spacing: .14em; }
.store-access__heading h1 { margin: 0; color: #22312e; font-size: clamp(1.45rem, 4vw, 2rem); font-weight: 800; }
.store-access__heading p:last-child { margin: .4rem 0 0; color: #71817c; font-size: .88rem; }

.store-active {
  display: flex;
  align-items: center;
  gap: .85rem;
  margin-bottom: 1.25rem;
  padding: 1rem 1.1rem;
  border: 1px solid #b9e5da;
  border-radius: 14px;
  background: #effaf7;
}

.store-active > div { display: grid; gap: .08rem; }
.store-active__icon,
.store-membership__icon { width: 38px; height: 38px; flex: 0 0 38px; border-radius: 50%; display: grid; place-items: center; background: #dff5ef; color: #21897e; }
.store-active span:not(.store-active__icon),
.store-active small { color: #71817c; font-size: .78rem; }
.store-active strong { color: #22312e; font-size: 1rem; }

.store-section { margin-bottom: 1.25rem; border: 1px solid #dce6e3; border-radius: 16px; background: #fff; box-shadow: 0 8px 28px rgba(34, 49, 46, .04); overflow: hidden; }
.store-section__head { padding: 1rem 1.1rem; border-bottom: 1px solid #e7efed; }
.store-section__head h2 { margin: 0; color: #22312e; font-size: 1rem; font-weight: 800; }
.store-section__head p { margin: .25rem 0 0; color: #71817c; font-size: .8rem; }
.store-section__body { padding: 0 1.1rem; }

.store-membership {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0.75rem;
  padding: .9rem 0;
  border-bottom: 1px solid #edf2f1;
}

.store-membership:last-child { border-bottom: 0; padding-bottom: 0; }
.store-membership__copy { display: grid; gap: .1rem; min-width: 0; }
.store-membership__copy strong { color: #22312e; overflow-wrap: anywhere; }
.store-membership__copy span { color: #71817c; font-size: .78rem; }
.store-membership .btn { margin-left: auto; white-space: nowrap; }

.store-membership__active {
  margin-left: auto;
  padding: .3rem .55rem;
  border-radius: 999px;
  background: #e1f6f0;
  color: #137b69;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}

.store-invitation { padding: .95rem 0; border-bottom: 1px solid #edf2f1; }
.store-invitation:last-child { border-bottom: 0; }
.store-invitation h3 { color: #22312e; }

@media (max-width: 575.98px) {
  .store-access { padding-top: 1.25rem; }
  .store-access__heading { margin-bottom: 1.2rem; }
  .store-section__head, .store-section__body { padding-left: .9rem; padding-right: .9rem; }
  .store-membership { gap: .55rem; }
  .store-membership__icon { display: none; }
}
</style>
