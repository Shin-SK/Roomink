<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const router = useRouter()
const customers = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const flagFilter = ref('')

const flagMap = {
  NONE: { text: 'なし', cls: '' },
  ATTENTION: { text: '要注意', cls: 'badge-pending' },
  BAN: { text: '出禁', cls: 'badge-banned' },
}

const filtered = computed(() => {
  let list = customers.value
  if (flagFilter.value) {
    list = list.filter(c => c.flag === flagFilter.value)
  }
  if (search.value.trim()) {
    const q = search.value.trim().toLowerCase()
    list = list.filter(c =>
      (c.phone || '').includes(q) ||
      (c.display_name || '').toLowerCase().includes(q)
    )
  }
  return list
})

onMounted(async () => {
  try {
    const data = await api.getCustomers()
    customers.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function goDetail(id) {
  router.push(`/op/customers/${id}`)
}
</script>

<template>
  <LayoutOperator>
    <template #title>顧客管理</template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else>
      <div class="card mb-4">
        <div class="card-header">
          <i class="ti ti-users"></i> 顧客一覧
        </div>
        <div class="card-body">
          <!-- 検索 -->
          <div class="mb-3">
            <input
              v-model="search"
              type="text"
              class="form-control"
              placeholder="電話番号 or 名前で検索..."
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

          <div v-if="!filtered.length" class="text-muted py-3 text-center">
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
                <td>{{ c.display_name || '—' }}</td>
                <td>{{ c.phone }}</td>
                <td>
                  <span
                    v-if="c.flag && c.flag !== 'NONE'"
                    class="badge"
                    :class="flagMap[c.flag]?.cls || 'bg-secondary'"
                  >{{ flagMap[c.flag]?.text || c.flag }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

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
