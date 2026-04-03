<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const selectedDate = ref(new Date().toISOString().slice(0, 10))
const rows = ref([])
const totals = ref({})
const settlementStatus = ref('OPEN')
const lockedAt = ref(null)
const lockedBy = ref(null)
const locking = ref(false)
const csvExportUrl = computed(() => api.getDailySettlementExportUrl(selectedDate.value))

async function fetchSettlement() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getDailySettlement(selectedDate.value)
    rows.value = data.rows || []
    totals.value = data.totals || {}
    settlementStatus.value = data.settlement_status || 'OPEN'
    lockedAt.value = data.locked_at || null
    lockedBy.value = data.locked_by || null
  } catch (e) {
    error.value = e.message
    rows.value = []
    totals.value = {}
    settlementStatus.value = 'OPEN'
  } finally {
    loading.value = false
  }
}

async function doLock() {
  if (!confirm('この日の清算を確定しますか？確定後は数値が固定されます。')) return
  locking.value = true
  error.value = ''
  try {
    await api.lockDailySettlement({
      date: selectedDate.value,
      rows: rows.value,
      totals: totals.value,
    })
    await fetchSettlement()
  } catch (e) {
    error.value = e.message
  } finally {
    locking.value = false
  }
}

async function doUnlock() {
  if (!confirm('この日の清算確定を解除しますか？都度計算に戻ります。')) return
  locking.value = true
  error.value = ''
  try {
    await api.unlockDailySettlement({ date: selectedDate.value })
    await fetchSettlement()
  } catch (e) {
    error.value = e.message
  } finally {
    locking.value = false
  }
}

onMounted(fetchSettlement)
watch(selectedDate, fetchSettlement)

function yen(n) {
  return `¥${Number(n || 0).toLocaleString()}`
}

function formatDt(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
</script>

<template>
  <LayoutOperator>
    <template #title>日給一覧</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span>
          <i class="ti ti-calculator"></i> 日給一覧
          <span v-if="settlementStatus === 'LOCKED'" class="badge bg-success ms-2">確定済</span>
          <span v-else class="badge bg-secondary ms-2">未確定</span>
        </span>
        <div class="d-flex gap-2">
          <a
            v-if="rows.length"
            :href="csvExportUrl"
            class="btn btn-outline-secondary btn-sm"
            target="_blank"
          >
            <i class="ti ti-download"></i> CSV
          </a>
          <button
            v-if="settlementStatus === 'OPEN' && rows.length"
            class="btn btn-success btn-sm"
            :disabled="locking"
            @click="doLock"
          >
            <i class="ti ti-lock"></i> この日を確定
          </button>
          <button
            v-if="settlementStatus === 'LOCKED'"
            class="btn btn-outline-warning btn-sm"
            :disabled="locking"
            @click="doUnlock"
          >
            <i class="ti ti-lock-open"></i> ロック解除
          </button>
        </div>
      </div>
      <div class="card-body">
        <!-- Date -->
        <div class="row mb-3">
          <div class="col-md-4">
            <input v-model="selectedDate" type="date" class="form-control" />
          </div>
          <div v-if="settlementStatus === 'LOCKED'" class="col-md-8 d-flex align-items-center">
            <small class="text-muted">
              <i class="ti ti-lock"></i>
              {{ formatDt(lockedAt) }} に {{ lockedBy || '—' }} が確定
            </small>
          </div>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!rows.length" class="text-muted text-center py-3">
          この日に出勤したキャストはいません
        </div>

        <div v-else class="table-responsive">
          <table class="table table-hover table-sm mb-0">
            <thead>
              <tr>
                <th>キャスト</th>
                <th>出勤</th>
                <th class="text-end">件数</th>
                <th class="text-end">コース売上</th>
                <th class="text-end">OP売上</th>
                <th class="text-end">バック率</th>
                <th class="text-end">バック額</th>
                <th class="text-end">雑費</th>
                <th class="text-end">ポイント</th>
                <th class="text-end">現金件数</th>
                <th class="text-end">現金預り</th>
                <th class="text-end fw-bold">振込額</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.cast_id">
                <td>{{ r.cast_name }}</td>
                <td class="text-muted" style="font-size: 0.8rem;">{{ r.shift }}</td>
                <td class="text-end">{{ r.order_count }}</td>
                <td class="text-end">{{ yen(r.course_sales) }}</td>
                <td class="text-end">{{ yen(r.options_sales) }}</td>
                <td class="text-end text-muted" style="font-size: 0.8rem;">
                  {{ r.course_back_rate }}%
                  <span v-if="r.option_fullback_enabled" class="badge bg-info ms-1" style="font-size: 0.6rem;">OP全額</span>
                </td>
                <td class="text-end">{{ yen(r.back_amount) }}</td>
                <td class="text-end text-danger">{{ r.expense_total ? '-' + yen(r.expense_total) : '—' }}</td>
                <td class="text-end" :class="r.point_total > 0 ? 'text-success' : r.point_total < 0 ? 'text-danger' : ''">
                  {{ r.point_total ? (r.point_total > 0 ? '+' : '') + r.point_total : '—' }}
                </td>
                <td class="text-end">{{ r.cash_order_count || '—' }}</td>
                <td class="text-end text-danger">{{ r.cash_sales_total ? '-' + yen(r.cash_sales_total) : '—' }}</td>
                <td class="text-end fw-bold" :class="r.net_pay < 0 ? 'text-danger' : ''">
                  {{ yen(r.net_pay) }}
                  <div v-if="r.net_pay < 0" class="small fw-normal" style="font-size: 0.65rem;">手元残 {{ yen(-r.net_pay) }}</div>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="table-light fw-bold">
                <td colspan="3">合計</td>
                <td class="text-end">{{ yen(totals.course_sales) }}</td>
                <td class="text-end">{{ yen(totals.options_sales) }}</td>
                <td></td>
                <td class="text-end">{{ yen(totals.back_amount) }}</td>
                <td class="text-end text-danger">{{ totals.expense_total ? '-' + yen(totals.expense_total) : '—' }}</td>
                <td class="text-end" :class="totals.point_total > 0 ? 'text-success' : totals.point_total < 0 ? 'text-danger' : ''">
                  {{ totals.point_total ? (totals.point_total > 0 ? '+' : '') + totals.point_total : '—' }}
                </td>
                <td class="text-end">{{ totals.cash_order_count || '—' }}</td>
                <td class="text-end text-danger">{{ totals.cash_sales_total ? '-' + yen(totals.cash_sales_total) : '—' }}</td>
                <td class="text-end" :class="totals.net_pay < 0 ? 'text-danger' : ''">{{ yen(totals.net_pay) }}</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div v-if="rows.length" class="mt-3 text-muted" style="font-size: 0.75rem;">
          <i class="ti ti-info-circle"></i>
          振込額 = バック額 - 雑費 + ポイント - 現金預り。現金払いはキャスト預かり分として控除。マイナス = キャスト手元残。
          <span v-if="settlementStatus === 'LOCKED'" class="fw-bold"> この日は確定済みのため、スナップショットを表示しています。</span>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
