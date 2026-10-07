<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const route = useRoute()
const selectedDate = ref(/^\d{4}-\d{2}-\d{2}$/.test(route.query.date || '') ? route.query.date : new Date().toISOString().slice(0, 10))
const rows = ref([])
const totals = ref({})
const settlementStatus = ref('OPEN')
const lockedAt = ref(null)
const lockedBy = ref(null)
const locking = ref(false)
const unlockReason = ref('')
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
  if (!unlockReason.value.trim()) {
    error.value = 'ロック解除の理由を入力してください。'
    return
  }
  if (!confirm('この日の清算確定を解除しますか？都度計算に戻ります。')) return
  locking.value = true
  error.value = ''
  try {
    await api.unlockDailySettlement({ date: selectedDate.value, reason: unlockReason.value.trim() })
    unlockReason.value = ''
    await fetchSettlement()
  } catch (e) {
    error.value = e.message
  } finally {
    locking.value = false
  }
}

onMounted(fetchSettlement)
watch(selectedDate, fetchSettlement)
watch(() => route.query.date, date => {
  if (/^\d{4}-\d{2}-\d{2}$/.test(date || '') && date !== selectedDate.value) selectedDate.value = date
})

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
        <div v-if="settlementStatus === 'LOCKED'" class="mb-3">
          <label class="form-label small fw-bold" for="settlement-unlock-reason">ロック解除理由</label>
          <textarea
            id="settlement-unlock-reason"
            v-model="unlockReason"
            class="form-control"
            rows="2"
            maxlength="500"
            placeholder="訂正が必要な理由を記録してください（必須）"
          ></textarea>
          <div class="form-text">解除前の確定内容・実行者・理由は監査記録として保存されます。</div>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!rows.length" class="text-muted text-center py-3">
          この日に出勤したキャストはいません
        </div>

        <div v-if="!loading && rows.some(row => row.compensation !== undefined)" class="mb-4">
          <h6 class="fw-bold mb-2">売上配分</h6>
          <div class="row g-2 mb-2">
            <div class="col-4"><div class="bg-light rounded p-2 text-center"><div class="small text-muted">お客様決済額</div><strong>{{ yen(totals.customer_payment_total ?? totals.total_sales) }}</strong></div></div>
            <div class="col-4"><div class="bg-light rounded p-2 text-center"><div class="small text-muted">報酬</div><strong class="text-primary">{{ yen(totals.compensation) }}</strong></div></div>
            <div class="col-4"><div class="bg-light rounded p-2 text-center"><div class="small text-muted">店舗配分</div><strong>{{ yen(totals.store_allocation) }}</strong></div></div>
          </div>
          <div v-for="row in rows" :key="'allocation-' + row.cast_id" class="d-flex flex-wrap align-items-center justify-content-between gap-2 border-bottom py-2 small">
            <strong>{{ row.cast_name }}</strong>
            <span>売上 {{ yen(row.total_sales) }}　お客様決済 {{ yen(row.customer_payment_total ?? row.total_sales) }}　報酬 <b class="text-primary">{{ yen(row.compensation) }}</b>　店舗配分 <b>{{ yen(row.store_allocation) }}</b></span>
          </div>
          <div class="small text-muted mt-2">報酬＝バック額−固定雑費−当日雑費。店舗配分＝お客様決済額−店舗側決済手数料−報酬。カードの上乗せ分は店舗配分に含まれます。</div>
        </div>
        <div v-else-if="!loading && settlementStatus === 'LOCKED' && rows.length" class="alert alert-info small">この日は旧形式で確定されているため、売上配分は表示できません。</div>

        <p v-if="!loading && rows.length" class="daily-settlement-scroll-hint d-md-none mb-2">
          <i class="ti ti-arrows-left-right" aria-hidden="true"></i>
          表は横にスクロールして確認できます
        </p>
        <div
          v-if="!loading && rows.length"
          class="table-responsive daily-settlement-table-wrap"
          role="region"
          aria-label="日給一覧の明細表"
          tabindex="0"
        >
          <table class="table table-hover table-sm mb-0 daily-settlement-table">
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
                  コース {{ r.course_back_rate }}%
                  <span class="badge bg-info ms-1" style="font-size: 0.6rem;">OP {{ r.option_back_rate ?? (r.option_fullback_enabled ? 100 : 0) }}%</span>
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
          振込額 = 報酬 + ポイント - 現金預り。現金払いはキャスト預かり分として控除。マイナス = キャスト手元残。
          <span v-if="settlementStatus === 'LOCKED'" class="fw-bold"> この日は確定済みのため、スナップショットを表示しています。</span>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.daily-settlement-table-wrap {
  -webkit-overflow-scrolling: touch;
}

/*
 * モバイルでは12列の情報量を維持する。表を無理に縮めると日本語が一文字ずつ
 * 折り返されるため、横スクロールを明示して列の可読性を優先する。
 */
.daily-settlement-table {
  min-width: 1080px;
}

.daily-settlement-table :is(th, td) {
  white-space: nowrap;
  vertical-align: middle;
}

.daily-settlement-table th:first-child,
.daily-settlement-table td:first-child {
  min-width: 6.5rem;
}

.daily-settlement-table th:nth-child(2),
.daily-settlement-table td:nth-child(2) {
  min-width: 6rem;
}

.daily-settlement-scroll-hint {
  color: var(--bs-secondary-color);
  font-size: 0.8rem;
}
</style>
