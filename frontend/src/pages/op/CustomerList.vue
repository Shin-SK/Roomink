<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const router = useRouter()
const isManager = computed(() => getAuthRole() === 'manager')
const customers = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const flagFilter = ref('')
const total = ref(0)
const offset = ref(0)
const pageSize = 50
let requestId = 0
let searchTimer

const flagMap = {
  NONE: { text: 'なし', cls: '' },
  ATTENTION: { text: '要注意', cls: 'badge-pending' },
  BAN: { text: '出禁', cls: 'badge-banned' },
}

const banTypeMap = {
  STORE_BAN: '店出禁',
  CAST_NG: '個別セラピNG',
}

const filtered = computed(() => customers.value)

async function loadCustomers(nextOffset = 0) {
  const currentRequest = ++requestId
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(nextOffset) })
  if (search.value.trim()) params.set('search', search.value.trim())
  if (flagFilter.value) params.set('flag', flagFilter.value)
  try {
    const data = await api.getCustomersPage(params.toString())
    if (currentRequest !== requestId) return
    customers.value = data.results || []
    total.value = data.count || 0
    offset.value = nextOffset
  } catch (e) {
    if (currentRequest !== requestId) return
    customers.value = []
    error.value = e.message
  } finally {
    if (currentRequest === requestId) loading.value = false
  }
}

watch([search, flagFilter], () => {
  ++requestId
  clearTimeout(searchTimer)
  customers.value = []
  total.value = 0
  offset.value = 0
  error.value = ''
  loading.value = true
  searchTimer = setTimeout(() => loadCustomers(), 250)
})

onMounted(() => loadCustomers())
onBeforeUnmount(() => { clearTimeout(searchTimer); ++requestId })

function goDetail(id) {
  router.push(`/op/customers/${id}`)
}

function exportCsv() {
  window.open(api.getCustomersExportUrl(), '_blank')
}
</script>

<template>
  <LayoutOperator>
    <template #title>顧客管理</template>
    <router-link to="/op/legacy-histories" class="btn btn-outline-secondary btn-sm mb-3">旧システムの利用履歴</router-link>

      <div class="card mb-4">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span><i class="ti ti-users"></i> 顧客一覧</span>
          <button
            v-if="isManager"
            class="btn btn-sm btn-outline-dark"
            @click="exportCsv"
          ><i class="ti ti-download"></i> CSVエクスポート</button>
        </div>
        <div class="card-body">
          <!-- 検索 -->
          <div class="mb-3">
            <input
              v-model="search"
              type="text"
              class="form-control"
              placeholder="電話番号・名前・メールで検索..."
            >
          </div>
          <!-- フィルタpill -->
          <div class="d-flex gap-2 mb-3 flex-wrap">
            <button
              class="btn btn-sm rounded-pill"
              :class="flagFilter === '' ? 'btn-dark' : 'btn-outline-secondary'"
              @click="flagFilter = ''"
            >すべて</button>
            <button
              class="btn btn-sm rounded-pill"
              :class="flagFilter === 'NONE' ? 'btn-dark' : 'btn-outline-secondary'"
              @click="flagFilter = 'NONE'"
            >フラグなし</button>
            <button
              class="btn btn-sm rounded-pill"
              :class="flagFilter === 'ATTENTION' ? 'btn-warning' : 'btn-outline-warning'"
              @click="flagFilter = 'ATTENTION'"
            >要注意</button>
            <button
              class="btn btn-sm rounded-pill"
              :class="flagFilter === 'BAN' ? 'btn-danger' : 'btn-outline-danger'"
              @click="flagFilter = 'BAN'"
            >出禁</button>
          </div>

          <div v-if="!loading && !error && total" class="d-flex align-items-center justify-content-between gap-2 mb-3">
            <small class="text-muted">{{ total }}件中 {{ offset + 1 }}〜{{ offset + filtered.length }}件</small>
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-outline-secondary" :disabled="offset === 0" @click="loadCustomers(offset - pageSize)">前へ</button>
              <button class="btn btn-sm btn-outline-secondary" :disabled="offset + pageSize >= total" @click="loadCustomers(offset + pageSize)">次へ</button>
            </div>
          </div>
          <div v-if="loading" class="text-center py-3" role="status">読み込み中…</div>
          <div v-else-if="error" class="alert alert-danger">
            {{ error }}
            <button class="btn btn-sm btn-outline-dark ms-2" @click="loadCustomers()">再試行</button>
          </div>
          <div v-else-if="!filtered.length" class="text-muted py-3 text-center">
            該当する顧客がいません
          </div>

          <table v-else class="table table-hover mb-0">
            <thead>
              <tr>
                <th>名前</th>
                <th>電話番号</th>
                <th>フラグ</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="c in filtered"
                :key="c.id"
                style="cursor: pointer;"
                @click="goDetail(c.id)"
              >
                <td>
                  {{ c.display_name || '—' }}
                  <span v-if="c.duplicate_count" class="badge bg-warning text-dark ms-1" style="font-size: 0.65rem;">
                    <i class="ti ti-copy"></i> 重複{{ c.duplicate_count }}件
                  </span>
                </td>
                <td>{{ c.phone }}</td>
                <td>
                  <span
                    v-if="c.flag && c.flag !== 'NONE'"
                    class="badge"
                    :class="flagMap[c.flag]?.cls || 'bg-secondary'"
                  >{{ flagMap[c.flag]?.text || c.flag }}</span>
                  <small v-if="c.flag === 'BAN' && banTypeMap[c.ban_type]" class="text-muted ms-1">{{ banTypeMap[c.ban_type] }}</small>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    <!-- FAB 新規作成 -->
    <router-link to="/op/customers/new" class="fab-btn">
      <i class="ti ti-plus"></i>
    </router-link>
  </LayoutOperator>
</template>

<style scoped>
.fab-btn {
  position: fixed;
  bottom: 90px;
  right: 20px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--bs-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  text-decoration: none;
  z-index: 100;
  transition: transform 0.15s;
}
.fab-btn:hover {
  transform: scale(1.1);
  color: #fff;
}
</style>
