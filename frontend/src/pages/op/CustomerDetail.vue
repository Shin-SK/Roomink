<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const props = defineProps({
  id: { type: [String, Number], required: true },
})

const router = useRouter()
const route = useRoute()
const customer = ref(null)
const loading = ref(true)
const error = ref('')

const isNew = computed(() => props.id === 'new')

// Edit / Create state
const editing = ref(false)
const saving = ref(false)
const editError = ref('')
const form = ref({ phone: '', display_name: '', flag: 'NONE', memo: '' })

const flagMap = {
  NONE: { text: 'なし', cls: '' },
  ATTENTION: { text: '要注意', cls: 'badge-pending' },
  BAN: { text: '出禁', cls: 'badge-banned' },
}

onMounted(async () => {
  if (isNew.value) {
    editing.value = true
    const qPhone = route.query.phone
    if (qPhone) {
      form.value.phone = qPhone
    }
    loading.value = false
    return
  }
  try {
    customer.value = await api.getCustomer(props.id)
  } catch (e) {
    error.value = e.message || '顧客が見つかりません'
  } finally {
    loading.value = false
  }
})

function startEdit() {
  editError.value = ''
  form.value = {
    phone: customer.value.phone,
    display_name: customer.value.display_name || '',
    flag: customer.value.flag || 'NONE',
    memo: customer.value.memo || '',
  }
  editing.value = true
}

function cancelEdit() {
  if (isNew.value) {
    router.push('/op/customers')
    return
  }
  editing.value = false
  editError.value = ''
}

async function save() {
  editError.value = ''
  saving.value = true
  try {
    if (isNew.value) {
      const body = {
        phone: form.value.phone,
        display_name: form.value.display_name,
        flag: form.value.flag,
        memo: form.value.memo,
      }
      const created = await api.createCustomer(body)
      const returnUrl = route.query.return
      if (returnUrl && typeof returnUrl === 'string' && returnUrl.startsWith('/')) {
        router.replace(returnUrl)
      } else {
        router.replace(`/op/customers/${created.id}`)
      }
    } else {
      const body = {
        display_name: form.value.display_name,
        flag: form.value.flag,
        memo: form.value.memo,
      }
      customer.value = await api.updateCustomer(props.id, body)
      editing.value = false
    }
  } catch (e) {
    editError.value = e.message
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push('/op/customers')
}
</script>

<template>
  <LayoutOperator>
    <template #title>{{ isNew ? '顧客新規作成' : '顧客詳細' }}</template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else-if="customer || isNew">
      <div class="mb-3">
        <button class="btn btn-outline-secondary btn-sm" @click="goBack">
          <i class="ti ti-arrow-left"></i> 顧客一覧
        </button>
      </div>

      <div class="card mb-4">
        <div class="card-header d-flex align-items-center justify-content-between">
          <span><i class="ti ti-user"></i> {{ isNew ? '新規顧客' : '顧客情報' }}</span>
          <button
            v-if="!isNew && !editing"
            class="btn btn-outline-primary btn-sm"
            @click="startEdit"
          >
            <i class="ti ti-edit"></i> 編集
          </button>
        </div>

        <!-- 閲覧モード -->
        <div v-if="!editing" class="card-body">
          <table class="table mb-0">
            <tbody>
              <tr>
                <th style="width: 120px;">ID</th>
                <td>{{ customer.id }}</td>
              </tr>
              <tr>
                <th>店舗</th>
                <td>{{ customer.store_name }}</td>
              </tr>
              <tr>
                <th>電話番号</th>
                <td>{{ customer.phone }}</td>
              </tr>
              <tr>
                <th>名前</th>
                <td>{{ customer.display_name || '—' }}</td>
              </tr>
              <tr>
                <th>フラグ</th>
                <td>
                  <span
                    v-if="customer.flag && customer.flag !== 'NONE'"
                    class="badge"
                    :class="flagMap[customer.flag]?.cls || 'bg-secondary'"
                  >{{ flagMap[customer.flag]?.text || customer.flag }}</span>
                  <span v-else class="text-muted">なし</span>
                </td>
              </tr>
              <tr>
                <th>メモ</th>
                <td style="white-space: pre-wrap;">{{ customer.memo || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 編集 / 新規作成モード -->
        <div v-else class="card-body">
          <div v-if="editError" class="alert alert-danger py-2 px-3 mb-3" style="font-size: 0.875rem;">
            {{ editError }}
          </div>
          <form @submit.prevent="save">
            <div class="mb-3">
              <label class="form-label">電話番号</label>
              <input
                v-if="isNew"
                v-model="form.phone"
                type="tel"
                class="form-control"
                placeholder="09012345678"
                required
              >
              <input
                v-else
                :value="customer.phone"
                type="text"
                class="form-control"
                disabled
              >
              <small v-if="isNew" class="text-muted">ハイフン入力可（自動で正規化されます）</small>
            </div>
            <div class="mb-3">
              <label class="form-label">名前</label>
              <input v-model="form.display_name" type="text" class="form-control" placeholder="表示名">
            </div>
            <div class="mb-3">
              <label class="form-label">フラグ</label>
              <select v-model="form.flag" class="form-select">
                <option value="NONE">なし</option>
                <option value="ATTENTION">要注意</option>
                <option value="BAN">出禁</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">メモ</label>
              <textarea v-model="form.memo" class="form-control" rows="3"></textarea>
            </div>
            <div class="d-flex gap-2">
              <button type="submit" class="btn btn-primary" :disabled="saving">
                {{ saving ? '保存中...' : (isNew ? '作成' : '保存') }}
              </button>
              <button type="button" class="btn btn-outline-secondary" @click="cancelEdit" :disabled="saving">
                キャンセル
              </button>
            </div>
          </form>
        </div>
      </div>
    </template>
  </LayoutOperator>
</template>
