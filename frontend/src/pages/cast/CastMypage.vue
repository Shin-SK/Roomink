<script setup>
import { ref, computed, onMounted } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const castName = ref('')
const avatarUrl = ref('')
const shift = ref(null)
const orders = ref([])
const totalOrders = ref(0)
const unconfirmedCount = ref(0)
const lineLinked = ref(false)
const lineLinkCode = ref('')
const lineAddFriendUrl = ref('')
const showLineModal = ref(false)
const codeCopied = ref(false)
const totalPoints = ref(0)
const pointHistory = ref([])

function today() {
  return new Date().toISOString().slice(0, 10)
}

onMounted(async () => {
  try {
    const data = await api.getCastToday(today())
    castName.value = data.cast_name
    avatarUrl.value = data.avatar_url
    shift.value = data.shift
    orders.value = data.orders
    totalOrders.value = data.total_orders
    unconfirmedCount.value = data.unconfirmed_count
    lineLinked.value = data.line_linked || false
    lineLinkCode.value = data.line_link_code || ''
    lineAddFriendUrl.value = data.line_add_friend_url || ''
    if (!lineLinked.value) showLineModal.value = true
    // ポイント取得
    try {
      const pts = await api.getCastPoints()
      totalPoints.value = pts.total_points || 0
      pointHistory.value = pts.history || []
    } catch (_) { /* ポイント取得失敗は致命的でない */ }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function doAck(order) {
  try {
    const updated = await api.ackOrder(order.id)
    const idx = orders.value.findIndex(o => o.id === order.id)
    if (idx !== -1) orders.value[idx] = updated
    unconfirmedCount.value = orders.value.filter(o => o.is_unconfirmed).length
  } catch (e) {
    alert(e.message)
  }
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function copyCode() {
  navigator.clipboard.writeText(lineLinkCode.value)
  codeCopied.value = true
  setTimeout(() => { codeCopied.value = false }, 2000)
}

function openLineFriend() {
  window.open(lineAddFriendUrl.value, '_blank')
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

function durationMin(order) {
  const s = new Date(order.start)
  const e = new Date(order.end)
  return Math.round((e - s) / 60000)
}
</script>

<template>
  <LayoutCast>
      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary"></div>
      </div>

      <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

      <template v-else>
        <!-- ページヘッダー -->
        <div class="ca-page-header d-flex align-items-center gap-3 mb-4">
          <div
            v-if="!avatarUrl"
            class="rounded-circle flex-shrink-0 d-flex align-items-center justify-content-center bg-light"
            style="width: 72px; aspect-ratio: 1/1;"
          >
            <i class="ti ti-user" style="font-size: 28px; color: var(--rk-primary)"></i>
          </div>
          <img
            v-else
            :src="avatarUrl"
            class="rounded-circle flex-shrink-0"
            style="width: 72px; aspect-ratio: 1/1; object-fit: cover;"
            alt=""
          >
          <div class="flex-grow-1">
            <div class="ca-page-header__title">{{ castName }}様</div>
            <div class="ca-page-header__sub" v-if="shift">
              <span class="time">
                <i class="ti ti-calendar-event"></i>{{ shift.start_time }}-{{ shift.end_time }}</span>
              <span class="room">
                <i class="ti ti-door"></i>{{ shift.room_name }}</span>
            </div>
          </div>
        </div>

        <!-- サマリーカード -->
        <div class="row g-2 mb-3">
          <div class="col-6">
            <div class="card text-center mb-0">
              <div class="card-body p-3">
                <div class="small text-muted mb-2">本日の予約</div>
                <div class="fs-4 fw-bold">{{ totalOrders }}本</div>
              </div>
            </div>
          </div>
          <div class="col-6">
            <div class="card text-center mb-0">
              <div class="card-body p-3">
                <div class="small text-muted mb-2">未確認</div>
                <div class="fs-4 fw-bold" :class="unconfirmedCount > 0 ? 'text-danger' : ''">{{ unconfirmedCount }}本</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ポイントカード -->
        <div v-if="totalPoints !== 0 || pointHistory.length" class="card mb-3">
          <div class="card-body">
            <div class="d-flex align-items-center justify-content-between mb-2">
              <div class="fw-bold"><i class="ti ti-star text-warning"></i> ポイント</div>
              <div class="fs-4 fw-bold">{{ totalPoints }} pt</div>
            </div>
            <div v-if="pointHistory.length" class="small">
              <div v-for="p in pointHistory.slice(0, 5)" :key="p.id" class="d-flex justify-content-between text-muted border-bottom py-1">
                <span>{{ p.date }} {{ p.reason || '' }}</span>
                <span :class="p.points >= 0 ? 'text-success' : 'text-danger'" class="fw-bold">{{ p.points >= 0 ? '+' : '' }}{{ p.points }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- LINE連携カード -->
        <div v-if="lineLinked" class="card mb-3 border-success">
          <div class="card-body">
            <div class="d-flex align-items-center gap-3">
              <div class="flex-shrink-0">
                <div class="rounded-circle d-flex align-items-center justify-content-center bg-success" style="width: 40px; height: 40px;">
                  <i class="ti ti-brand-line" style="font-size: 20px; color: #fff;"></i>
                </div>
              </div>
              <div class="flex-grow-1">
                <div class="fw-bold mb-1">LINE連携</div>
                <div class="small text-success"><i class="ti ti-check"></i> 連携済み — リマインド通知が届きます</div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="card mb-3 border-warning border-2" style="cursor: pointer;" @click="showLineModal = true">
          <div class="card-body">
            <div class="d-flex align-items-center gap-3">
              <div class="flex-shrink-0">
                <div class="rounded-circle d-flex align-items-center justify-content-center bg-warning" style="width: 40px; height: 40px;">
                  <i class="ti ti-brand-line" style="font-size: 20px; color: #fff;"></i>
                </div>
              </div>
              <div class="flex-grow-1">
                <div class="fw-bold mb-1">LINE連携が必要です</div>
                <div class="small text-muted">タップして連携手順を確認 <i class="ti ti-chevron-right"></i></div>
              </div>
            </div>
          </div>
        </div>

        <!-- LINE連携モーダル -->
        <Teleport to="body">
          <div v-if="showLineModal && !lineLinked" class="line-modal-overlay" @click.self="showLineModal = false">
            <div class="line-modal">
              <div class="line-modal-header">
                <div class="d-flex align-items-center gap-2">
                  <div class="rounded-circle d-flex align-items-center justify-content-center" style="width: 36px; height: 36px; background: #06C755;">
                    <i class="ti ti-brand-line" style="font-size: 18px; color: #fff;"></i>
                  </div>
                  <span class="fw-bold fs-5">LINE連携</span>
                </div>
                <button class="btn btn-sm btn-light rounded-circle" @click="showLineModal = false" style="width: 32px; height: 32px; padding: 0;">
                  <i class="ti ti-x"></i>
                </button>
              </div>

              <div class="line-modal-body">
                <p class="text-muted small mb-3">出勤リマインドを受け取るためにLINE連携が必要です。</p>

                <!-- ステップ -->
                <div class="line-step">
                  <div class="line-step-num">1</div>
                  <div class="line-step-content">
                    <div class="fw-bold mb-2">連携コードをコピー</div>
                    <div class="line-code-box" @click="copyCode">
                      <span class="line-code">{{ lineLinkCode }}</span>
                      <span class="line-code-copy" :class="{ copied: codeCopied }">
                        <i :class="codeCopied ? 'ti ti-check' : 'ti ti-copy'"></i>
                        {{ codeCopied ? 'コピー済' : 'コピー' }}
                      </span>
                    </div>
                  </div>
                </div>

                <div class="line-step">
                  <div class="line-step-num">2</div>
                  <div class="line-step-content">
                    <div class="fw-bold mb-2">公式LINEを友だち追加してコードを送信</div>
                    <button class="btn w-100 text-white fw-bold" style="background: #06C755;" @click="openLineFriend">
                      <i class="ti ti-brand-line me-1"></i> 友だち追加する
                    </button>
                    <div class="small text-muted mt-2">友だち追加後、トーク画面でコピーしたコードを送信してください</div>
                  </div>
                </div>

                <div class="line-step">
                  <div class="line-step-num">3</div>
                  <div class="line-step-content">
                    <div class="fw-bold">連携完了！</div>
                    <div class="small text-muted mb-2">コード送信後、自動で連携されます。</div>
                    <button class="btn btn-sm btn-outline-success w-100" @click="location.reload()">
                      <i class="ti ti-refresh me-1"></i> ページを再読み込み
                    </button>
                  </div>
                </div>
              </div>

              <div class="line-modal-footer">
                <button class="btn btn-outline-secondary w-100" @click="showLineModal = false">あとで設定する</button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- 未確認警告カード -->
        <div v-if="unconfirmedCount > 0" class="alert alert-warning d-flex align-items-center gap-3 mb-4">
          <i class="ti ti-alert-triangle fs-4 flex-shrink-0"></i>
          <div class="flex-grow-1">
            <div class="fw-bold mb-1">未確認の予約があります</div>
            <div class="small">予約内容を確認して「確認する」ボタンを押してください</div>
          </div>
        </div>

        <!-- 予約一覧 -->
        <div class="rk-section-header"><i class="ti ti-calendar-event"></i> 予約一覧</div>

        <div
          v-for="order in orders"
          :key="order.id"
          class="card mb-3"
          :class="order.is_unconfirmed ? 'border-warning border-2' : ''"
        >
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <div>
                <div class="fw-bold fs-5">{{ formatTime(order.start) }} – {{ formatTime(order.end) }}</div>
                <div class="small text-muted">{{ durationMin(order) }}分</div>
              </div>
              <span
                class="badge"
                :class="order.is_unconfirmed ? 'badge-unconfirmed' : 'badge-approved'"
              >{{ order.is_unconfirmed ? '未確認' : '確認済' }}</span>
            </div>
            <div class="small text-muted mb-2">
              <div><i class="ti ti-door"></i> {{ order.room_name }}</div>
              <div><i class="ti ti-currency-yen"></i> {{ formatYen(order.course_price) }}</div>
            </div>
            <div class="bg-light p-2 rounded small mb-3">
              <i class="ti ti-note"></i> {{ order.memo || '備考なし' }}
            </div>
            <button
              v-if="order.is_unconfirmed"
              class="btn btn-sm btn-warning w-100"
              @click="doAck(order)"
            >
              <i class="ti ti-check"></i> 確認する
            </button>
            <button
              v-else
              class="btn btn-sm btn-outline-primary w-100"
              disabled
            >
              <i class="ti ti-check"></i> 確認済
            </button>
          </div>
        </div>

        <div v-if="orders.length === 0" class="text-muted text-center py-4">
          本日の予約はありません
        </div>

        <!-- 注意事項 -->
        <div class="card mb-3">
          <button class="card-header btn btn-link w-100 text-start d-flex justify-content-between align-items-center" data-bs-toggle="collapse" data-bs-target="#castNotes" aria-expanded="false">
            <span><i class="ti ti-info-circle"></i> 注意事項</span>
            <i class="ti ti-chevron-down"></i>
          </button>
          <div class="collapse" id="castNotes">
            <div class="card-body">
              <ul class="mb-0 ps-3">
                <li>予約内容を確認したら「確認する」ボタンを押してください</li>
                <li>予約開始15分前までに準備を完了してください</li>
                <li>遅刻やキャンセルの連絡があった場合は、すぐに運営に報告してください</li>
                <li>顧客情報は絶対に外部に漏らさないでください</li>
              </ul>
            </div>
          </div>
        </div>

        <a href="tel:03-1234-5678" class="card text-decoration-none text-reset mb-4 mt-4">
          <div class="card-body d-flex align-items-center gap-3">
            <div class="flex-shrink-0">
              <div class="rounded-circle d-flex align-items-center justify-content-center bg-light" style="width: 44px; height: 44px;">
                <i class="ti ti-phone" style="color: var(--rk-primary); font-size: 22px;"></i>
              </div>
            </div>
            <div class="flex-grow-1">
              <div class="fw-bold mb-1">困ったときは運営へ</div>
              <div class="small text-muted">タップして電話する<i class="ti ti-chevron-right text-muted"></i>
              </div>
            </div>
          </div>
        </a>

        <!-- フッターメッセージ -->
        <div class="text-center mb-5">
          <p class="text-muted" style="font-size: 0.8125rem;">本日もよろしくお願いします！</p>
        </div>

      </template>
  </LayoutCast>
</template>

<style scoped>
.line-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0;
}
.line-modal {
  background: #fff;
  border-radius: 20px 20px 0 0;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideUp 0.25s ease-out;
}
@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}
.line-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 12px;
  border-bottom: 1px solid #eee;
}
.line-modal-body {
  padding: 20px;
}
.line-modal-footer {
  padding: 12px 20px 24px;
}
.line-step {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.line-step-num {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #06C755;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 14px;
}
.line-step-content {
  flex: 1;
  min-width: 0;
}
.line-code-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f5f5f5;
  border: 2px dashed #ccc;
  border-radius: 10px;
  padding: 12px 16px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.line-code-box:active {
  border-color: #06C755;
}
.line-code {
  font-family: monospace;
  font-size: 1.5rem;
  font-weight: bold;
  letter-spacing: 4px;
}
.line-code-copy {
  font-size: 0.75rem;
  color: #888;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.line-code-copy.copied {
  color: #06C755;
}
</style>
