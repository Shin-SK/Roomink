<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import LayoutCustomer from '../../components/LayoutCustomer.vue'
import { api } from '../../api.js'

const route = useRoute()
const loading = ref(true)
const error = ref('')
const order = ref(null)

onMounted(async () => {
  try {
    order.value = await api.getCustomerReservation(route.params.id)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function formatDateRange(start, end) {
  if (!start || !end) return ''
  const s = new Date(start)
  const e = new Date(end)
  const days = ['日','月','火','水','木','金','土']
  const mm = String(s.getMonth()+1).padStart(2,'0')
  const dd = String(s.getDate()).padStart(2,'0')
  const sh = String(s.getHours()).padStart(2,'0')
  const sm = String(s.getMinutes()).padStart(2,'0')
  const eh = String(e.getHours()).padStart(2,'0')
  const em = String(e.getMinutes()).padStart(2,'0')
  return `${s.getFullYear()}-${mm}-${dd} (${days[s.getDay()]}) ${sh}:${sm}-${eh}:${em}`
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

function statusBadge(s) {
  if (s === 'CONFIRMED') return 'badge-approved'
  if (s === 'REQUESTED') return 'badge-pending'
  if (s === 'CANCELLED') return 'bg-secondary'
  if (s === 'DONE') return 'bg-success'
  return 'badge-primary'
}
</script>

<template>
  <LayoutCustomer>
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else-if="order">
      <h1 style="font-size: 2rem; margin-bottom: 1rem;">予約詳細</h1>
      <p class="text-muted mb-4">予約番号: #{{ order.id }}</p>

      <!-- ステータス -->
      <div
        class="alert"
        :class="order.status === 'CONFIRMED' || order.status === 'DONE' ? 'alert-success' : order.status === 'CANCELLED' ? 'alert-secondary' : 'alert-warning'"
      >
        <strong>
          <i class="ti" :class="order.status === 'CANCELLED' ? 'ti-x' : 'ti-check'"></i>
          {{ order.status_display }}
        </strong>
      </div>

      <!-- 予約情報 -->
      <div class="card">
        <div class="card-header">予約情報</div>
        <div class="card-body">
          <table class="table mb-0">
            <tbody>
              <tr>
                <th style="width: 130px;">予約日時</th>
                <td><strong>{{ formatDateRange(order.start, order.end) }}</strong></td>
              </tr>
              <tr>
                <th>セラピスト</th>
                <td>{{ order.cast_name }}</td>
              </tr>
              <tr>
                <th>コース</th>
                <td>{{ order.course_name }} ({{ formatYen(order.course_price) }})</td>
              </tr>
              <tr v-if="order.options.length">
                <th>オプション</th>
                <td>{{ order.options.join(', ') }} ({{ formatYen(order.options_price) }})</td>
              </tr>
              <tr v-if="order.extension_name">
                <th>延長</th>
                <td>{{ order.extension_name }} ({{ formatYen(order.extension_price) }})</td>
              </tr>
              <tr v-if="order.nomination_fee_name">
                <th>指名料</th>
                <td>{{ order.nomination_fee_name }} ({{ formatYen(order.nomination_fee_price) }})</td>
              </tr>
              <tr v-if="order.discount_name">
                <th>割引</th>
                <td>{{ order.discount_name }} (-{{ formatYen(order.discount_amount) }})</td>
              </tr>
              <tr>
                <th>料金</th>
                <td><strong>{{ formatYen(order.total_price) }}</strong></td>
              </tr>
              <tr>
                <th>ルーム</th>
                <td>{{ order.room_name }}</td>
              </tr>
              <tr>
                <th>ステータス</th>
                <td><span class="badge" :class="statusBadge(order.status)">{{ order.status_display }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 当日の流れ -->
      <div class="card">
        <div class="card-header">
          <i class="ti ti-clock"></i> 当日の流れ
        </div>
        <div class="card-body">
          <ol class="mb-0">
            <li class="mb-2">
              <strong>15分前を目安にご来店ください</strong><br>
              <small class="text-muted">受付にて予約番号をお伝えください</small>
            </li>
            <li class="mb-2">
              <strong>お支払い</strong><br>
              <small class="text-muted">現金またはクレジットカードがご利用いただけます</small>
            </li>
            <li class="mb-2">
              <strong>施術開始</strong><br>
              <small class="text-muted">担当セラピストがご案内します</small>
            </li>
          </ol>
        </div>
      </div>

      <!-- 注意事項 -->
      <div class="card">
        <div class="card-header">
          <i class="ti ti-alert-circle"></i> 注意事項
        </div>
        <div class="card-body">
          <ul class="mb-0">
            <li class="mb-2">ご予約時間に遅れる場合は、必ずお電話でご連絡ください</li>
            <li class="mb-2">無断キャンセルの場合、次回以降のご予約をお断りする場合があります</li>
            <li class="mb-2">キャンセルは24時間前までにお願いします</li>
            <li class="mb-2">体調不良の場合は無理をせず、予約変更をご検討ください</li>
          </ul>
        </div>
      </div>

      <!-- キャンセル・変更 -->
      <div class="card">
        <div class="card-header">
          <i class="ti ti-calendar-x"></i> キャンセル・変更について
        </div>
        <div class="card-body">
          <p class="mb-3">
            予約の変更やキャンセルが必要な場合は、お電話でご連絡ください。
          </p>
          <a href="tel:03-1234-5678" class="btn btn-outline-primary">
            <i class="ti ti-phone"></i> 電話する
          </a>
        </div>
      </div>

      <!-- 困ったときは -->
      <div class="alert alert-info">
        <strong><i class="ti ti-help"></i> 困ったときは</strong><br>
        わからないことがあれば、お気軽にお問い合わせください。<br>
        <strong>電話:</strong> 03-1234-5678
      </div>

      <!-- アクション -->
      <div class="text-center mb-5">
        <router-link to="/cu/mypage" class="btn btn-primary btn-lg">
          <i class="ti ti-arrow-left"></i> マイページに戻る
        </router-link>
      </div>
    </template>
  </LayoutCustomer>
</template>
