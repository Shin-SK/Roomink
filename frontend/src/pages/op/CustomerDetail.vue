<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

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
const form = ref({ phone: '', display_name: '', flag: 'NONE', ban_type: 'NONE', memo: '', staff_memo: '' })
const duplicates = ref([])
const createWarnings = ref([])
const isManager = computed(() => getAuthRole() === 'manager')
const merging = ref(false)
const mergeTarget = ref(null)
const showMergeConfirm = ref(false)

function openMerge(dup) {
  mergeTarget.value = dup
  showMergeConfirm.value = true
}

async function executeMerge() {
  if (!mergeTarget.value) return
  merging.value = true
  try {
    await api.mergeCustomer(props.id, mergeTarget.value.id)
    showMergeConfirm.value = false
    mergeTarget.value = null
    // 再読み込み
    customer.value = await api.getCustomer(props.id)
    api.getCustomerDuplicates(props.id).then(data => {
      duplicates.value = Array.isArray(data) ? data : []
    }).catch(() => {})
  } catch (e) {
    alert(e.message)
  } finally {
    merging.value = false
  }
}
let checkTimer = null

function scheduleCheckDuplicate() {
  if (!isNew.value) return
  clearTimeout(checkTimer)
  checkTimer = setTimeout(async () => {
    const phone = form.value.phone.trim()
    const name = form.value.display_name.trim()
    if (!phone && !name) { createWarnings.value = []; return }
    try {
      const data = await api.checkCustomerDuplicate(phone, name)
      createWarnings.value = Array.isArray(data) ? data : []
    } catch (_) {
      createWarnings.value = []
    }
  }, 400)
}

watch(() => form.value.phone, scheduleCheckDuplicate)
watch(() => form.value.display_name, scheduleCheckDuplicate)

const flagMap = {
  NONE: { text: 'なし', cls: '' },
  ATTENTION: { text: '要注意', cls: 'badge-pending' },
  BAN: { text: '出禁', cls: 'badge-banned' },
}

const banTypeMap = {
  NONE: 'なし',
  STORE_BAN: '店出禁',
  CAST_NG: '個別セラピNG',
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
    // 重複候補を非同期で取得
    api.getCustomerDuplicates(props.id).then(data => {
      duplicates.value = Array.isArray(data) ? data : []
    }).catch(() => {})
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
    ban_type: customer.value.ban_type || 'NONE',
    memo: customer.value.memo || '',
    staff_memo: customer.value.staff_memo || '',
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
        ban_type: form.value.ban_type,
        memo: form.value.memo,
        staff_memo: form.value.staff_memo,
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
        ban_type: form.value.ban_type,
        memo: form.value.memo,
        staff_memo: form.value.staff_memo,
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
              <tr v-if="customer.flag === 'BAN'">
                <th>出禁種別</th>
                <td>{{ banTypeMap[customer.ban_type] || 'なし' }}</td>
              </tr>
              <tr>
                <th>お客様備考</th>
                <td style="white-space: pre-wrap;">{{ customer.memo || '—' }}</td>
              </tr>
              <tr>
                <th>運営専用メモ</th>
                <td style="white-space: pre-wrap;">{{ customer.staff_memo || '—' }}</td>
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

            <!-- 新規作成時の重複警告 -->
            <div v-if="isNew && createWarnings.length" class="alert alert-warning py-2 px-3 mb-3" style="font-size: 0.85rem;">
              <div class="fw-bold mb-1"><i class="ti ti-alert-triangle"></i> 既存顧客の可能性があります</div>
              <div v-for="w in createWarnings" :key="w.id" class="d-flex align-items-center justify-content-between py-1 border-bottom">
                <span>
                  {{ w.display_name || '—' }} ({{ w.phone }})
                  <span v-if="w.flag === 'BAN'" class="badge badge-banned ms-1">出禁</span>
                  <span v-else-if="w.flag === 'ATTENTION'" class="badge badge-pending ms-1">要注意</span>
                  <small class="text-muted ms-1">{{ w.reason }}</small>
                </span>
                <router-link :to="`/op/customers/${w.id}`" class="btn btn-outline-primary btn-sm py-0 px-2" style="font-size: 0.75rem;">
                  詳細
                </router-link>
              </div>
              <small class="text-muted mt-1 d-block">そのまま作成も可能です。</small>
            </div>

            <div class="mb-3">
              <label class="form-label">フラグ</label>
              <select v-model="form.flag" class="form-select">
                <option value="NONE">なし</option>
                <option value="ATTENTION">要注意</option>
                <option value="BAN">出禁</option>
              </select>
            </div>
            <div v-if="form.flag === 'BAN'" class="mb-3">
              <label class="form-label">出禁種別</label>
              <select v-model="form.ban_type" class="form-select">
                <option value="NONE">なし</option>
                <option value="STORE_BAN">店出禁</option>
                <option value="CAST_NG">個別セラピNG</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">お客様備考</label>
              <textarea v-model="form.memo" class="form-control" rows="3" placeholder="お客様・セラピスト・運営が共通で見られるメモ"></textarea>
            </div>
            <div class="mb-3">
              <label class="form-label">運営専用メモ</label>
              <textarea v-model="form.staff_memo" class="form-control" rows="3" placeholder="運営のみが閲覧可能なメモ"></textarea>
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
      <!-- 重複候補 -->
      <div v-if="!isNew && duplicates.length" class="card mb-4 border-warning">
        <div class="card-header bg-warning bg-opacity-10">
          <i class="ti ti-alert-triangle text-warning"></i> 重複候補（{{ duplicates.length }}件）
        </div>
        <div class="card-body p-0">
          <table class="table table-sm mb-0">
            <thead>
              <tr>
                <th>名前</th>
                <th>電話番号</th>
                <th>フラグ</th>
                <th>理由</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in duplicates" :key="d.id">
                <td>{{ d.display_name || '—' }}</td>
                <td>{{ d.phone }}</td>
                <td>
                  <span v-if="d.flag === 'BAN'" class="badge badge-banned">{{ d.ban_type === 'STORE_BAN' ? '店出禁' : d.ban_type === 'CAST_NG' ? '個別NG' : '出禁' }}</span>
                  <span v-else-if="d.flag === 'ATTENTION'" class="badge badge-pending">要注意</span>
                </td>
                <td><span class="badge bg-secondary">{{ d.reason }}</span></td>
                <td class="d-flex gap-1">
                  <router-link :to="`/op/customers/${d.id}`" class="btn btn-outline-primary btn-sm">
                    <i class="ti ti-external-link"></i>
                  </router-link>
                  <button
                    v-if="isManager"
                    class="btn btn-outline-danger btn-sm"
                    @click="openMerge(d)"
                    title="この顧客を統合する"
                  >
                    <i class="ti ti-git-merge"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="px-3 py-2 text-muted" style="font-size: 0.75rem;">
            <i class="ti ti-info-circle"></i> 統合ボタンで相手の予約・通話履歴をこの顧客に寄せて統合できます（manager のみ）。
          </div>
        </div>
      </div>

      <!-- 統合確認モーダル -->
      <div v-if="showMergeConfirm" class="modal d-block" style="background: rgba(0,0,0,0.4);" @click.self="showMergeConfirm = false">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header bg-danger text-white">
              <h5 class="modal-title"><i class="ti ti-alert-triangle me-1"></i> 顧客統合の確認</h5>
              <button type="button" class="btn-close btn-close-white" @click="showMergeConfirm = false"></button>
            </div>
            <div class="modal-body">
              <div class="alert alert-danger mb-3">
                <strong>この操作は取り消せません。</strong><br>
                統合対象の顧客は削除され、予約・通話履歴がこの顧客に移されます。
              </div>

              <table class="table table-sm mb-3">
                <tbody>
                  <tr>
                    <th style="width: 100px;">残す顧客</th>
                    <td>
                      <strong>{{ customer.display_name || '—' }}</strong> ({{ customer.phone }})<br>
                      <small class="text-muted">ID: {{ customer.id }}</small>
                    </td>
                  </tr>
                  <tr v-if="mergeTarget">
                    <th>統合する顧客</th>
                    <td>
                      <strong>{{ mergeTarget.display_name || '—' }}</strong> ({{ mergeTarget.phone }})<br>
                      <small class="text-muted">ID: {{ mergeTarget.id }} — この顧客は削除されます</small>
                      <span v-if="mergeTarget.flag === 'BAN'" class="badge badge-banned ms-1">出禁</span>
                      <span v-else-if="mergeTarget.flag === 'ATTENTION'" class="badge badge-pending ms-1">要注意</span>
                    </td>
                  </tr>
                </tbody>
              </table>

              <div class="small text-muted">
                <ul class="mb-0 ps-3">
                  <li>予約・通話履歴は「残す顧客」に移されます</li>
                  <li>出禁/要注意フラグは強い方が残ります</li>
                  <li>メモは手動で見直しを推奨します</li>
                </ul>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="showMergeConfirm = false">キャンセル</button>
              <button class="btn btn-danger" :disabled="merging" @click="executeMerge">
                {{ merging ? '統合中...' : '統合を実行する' }}
              </button>
            </div>
          </div>
        </div>
      </div>

    </template>
  </LayoutOperator>
</template>
