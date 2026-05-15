<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  customer: { type: Object, default: null },
  recentOrders: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  searchedPhone: { type: String, default: '' },
  error: { type: String, default: '' },
  callLogs: { type: Array, default: () => [] },
  callLogsLoading: { type: Boolean, default: false },
  callLogsError: { type: String, default: '' },
  savingMemo: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'create-new', 'close', 'add-memo'])

const banTypeLabel = computed(() => {
  if (!props.customer) return ''
  const t = props.customer.ban_type
  if (t === 'STORE_BAN') return '店舗BAN'
  if (t === 'CAST_NG') return 'キャストNG'
  return ''
})

const sortedOrders = computed(() => {
  return [...(props.recentOrders || [])]
    .sort((a, b) => new Date(b.start) - new Date(a.start))
    .slice(0, 5)
})

const cancelledCount = computed(() =>
  (props.recentOrders || []).filter(o => o.status === 'CANCELLED').length
)

const lastOrder = computed(() => {
  const valid = sortedOrders.value.find(o => o.status !== 'CANCELLED')
  return valid || sortedOrders.value[0] || null
})

const sortedCallLogs = computed(() =>
  [...(props.callLogs || [])].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  )
)

function pad2(n) { return String(n).padStart(2, '0') }
function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s)
  return `${d.getFullYear()}/${pad2(d.getMonth() + 1)}/${pad2(d.getDate())}`
}
function fmtDateTime(s) {
  if (!s) return ''
  const d = new Date(s)
  return `${fmtDate(s)} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}
function statusLabel(s) {
  return ({
    REQUESTED: '確定待ち',
    CONFIRMED: '確定',
    IN_PROGRESS: '対応中',
    DONE: '完了',
    CANCELLED: 'キャンセル',
  })[s] || s
}

const memoBody = ref('')

function submitMemo() {
  const body = memoBody.value.trim()
  if (!body) return
  if (props.savingMemo) return
  emit('add-memo', body)
}

// 保存完了で savingMemo が false に戻ったタイミングで入力欄をクリア
let wasSaving = false
watch(
  () => props.savingMemo,
  (v) => {
    if (wasSaving && !v) memoBody.value = ''
    wasSaving = v
  }
)
</script>

<template>
  <div class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="emit('close')">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="ti ti-user me-1"></i>顧客情報
            <span v-if="searchedPhone" class="text-muted ms-2" style="font-size: 0.875rem;">{{ searchedPhone }}</span>
          </h5>
          <button type="button" class="btn-close" @click="emit('close')"></button>
        </div>

        <div class="modal-body">
          <div v-if="loading" class="text-center py-4">
            <div class="spinner-border text-primary"></div>
          </div>

          <div v-else-if="error" class="alert alert-danger py-2 px-3 mb-0">{{ error }}</div>

          <template v-else>
            <div v-if="!customer" class="text-center py-3">
              <p class="text-muted mb-2">該当顧客なし</p>
              <p v-if="searchedPhone" class="mb-3"><strong>{{ searchedPhone }}</strong></p>
              <button class="btn btn-primary" @click="emit('create-new', searchedPhone)">
                <i class="ti ti-plus me-1"></i>この番号で新規顧客作成
              </button>
            </div>

            <div v-else>
              <div v-if="customer.flag === 'BAN'" class="alert alert-danger py-2 px-3 mb-3">
                <i class="ti ti-ban me-1"></i><strong>出禁顧客</strong>
                <span v-if="banTypeLabel">（{{ banTypeLabel }}）</span>
              </div>
              <div v-else-if="customer.flag === 'ATTENTION'" class="alert alert-warning py-2 px-3 mb-3">
                <i class="ti ti-alert-triangle me-1"></i><strong>要注意顧客</strong>
              </div>

              <div class="row g-2 mb-3">
                <div class="col-6">
                  <small class="text-muted">顧客名</small>
                  <div class="fw-bold">{{ customer.display_name || '(名前未登録)' }}</div>
                </div>
                <div class="col-6">
                  <small class="text-muted">電話番号</small>
                  <div class="fw-bold">{{ customer.phone }}</div>
                </div>
              </div>

              <div v-if="customer.memo" class="mb-2">
                <small class="text-muted">顧客メモ</small>
                <div class="border rounded p-2 rk-cic-memo">{{ customer.memo }}</div>
              </div>
              <div v-if="customer.staff_memo" class="mb-3">
                <small class="text-muted">運営メモ</small>
                <div class="border rounded p-2 bg-light rk-cic-memo">{{ customer.staff_memo }}</div>
              </div>

              <hr />

              <div class="d-flex align-items-center justify-content-between mb-2">
                <h6 class="mb-0"><i class="ti ti-history me-1"></i>過去予約</h6>
                <small v-if="cancelledCount > 0" class="text-danger">キャンセル {{ cancelledCount }}件</small>
              </div>

              <div v-if="sortedOrders.length === 0" class="text-muted small">過去予約はありません</div>

              <div v-else>
                <div v-if="lastOrder" class="border rounded p-2 mb-2 bg-light rk-cic-last">
                  <div class="text-muted small">前回利用</div>
                  <div class="fw-bold">{{ fmtDateTime(lastOrder.start) }}</div>
                  <div>担当: {{ lastOrder.cast_name || '-' }} / コース: {{ lastOrder.course_name || '-' }}</div>
                </div>

                <ul class="list-group list-group-flush rk-cic-history">
                  <li
                    v-for="o in sortedOrders"
                    :key="o.id"
                    class="list-group-item d-flex justify-content-between align-items-center"
                  >
                    <span>
                      {{ fmtDate(o.start) }} — {{ o.cast_name || '-' }} / {{ o.course_name || '-' }}
                    </span>
                    <span
                      class="badge"
                      :class="o.status === 'CANCELLED' ? 'bg-danger' : 'bg-secondary'"
                    >{{ statusLabel(o.status) }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <slot name="call-history">
              <hr class="my-3" />

              <div class="mb-2">
                <h6 class="mb-2"><i class="ti ti-phone me-1"></i>架電/問い合わせ履歴</h6>

                <div v-if="callLogsLoading" class="text-muted small">読み込み中...</div>
                <div v-else-if="callLogsError" class="alert alert-warning py-1 px-2 mb-2" style="font-size: 0.8rem;">{{ callLogsError }}</div>
                <div v-else-if="sortedCallLogs.length === 0" class="text-muted small">履歴なし</div>

                <ul v-else class="list-group list-group-flush rk-cic-calllogs">
                  <li
                    v-for="log in sortedCallLogs"
                    :key="log.id"
                    class="list-group-item"
                  >
                    <div class="d-flex justify-content-between align-items-center">
                      <small class="text-muted">
                        {{ fmtDateTime(log.created_at) }}
                        — {{ log.assigned_to_label || '-' }}
                        <span v-if="log.from_phone" class="ms-1">({{ log.from_phone }})</span>
                      </small>
                      <span class="badge bg-secondary">{{ log.status }}</span>
                    </div>
                    <div v-if="log.notes && log.notes.length" class="mt-1">
                      <div
                        v-for="n in log.notes"
                        :key="n.id"
                        class="rk-cic-note"
                      >
                        <i class="ti ti-message-2 me-1"></i>{{ n.body }}
                      </div>
                    </div>
                    <div v-else class="text-muted small mt-1">メモなし</div>
                  </li>
                </ul>
              </div>

              <div class="rk-cic-memoform">
                <label class="form-label mb-1">
                  <i class="ti ti-plus me-1"></i>不成約・問い合わせメモを残す
                </label>
                <textarea
                  v-model="memoBody"
                  class="form-control form-control-sm"
                  rows="2"
                  placeholder="例: 料金で検討 / 希望キャスト不在 / 折り返し希望 など"
                  :disabled="savingMemo"
                ></textarea>
                <div class="d-flex justify-content-end mt-1">
                  <button
                    class="btn btn-sm btn-outline-primary"
                    :disabled="savingMemo || !memoBody.trim()"
                    @click="submitMemo"
                  >
                    {{ savingMemo ? '保存中...' : 'メモ追加' }}
                  </button>
                </div>
              </div>
            </slot>
          </template>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="emit('close')">閉じる</button>
          <button
            v-if="customer"
            class="btn btn-primary"
            :disabled="customer.flag === 'BAN'"
            @click="emit('select', customer)"
          >
            <i class="ti ti-calendar-plus me-1"></i>この顧客で予約作成
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
