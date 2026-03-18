<script setup>
import { useRoute } from 'vue-router'
import LayoutCustomer from '../../components/LayoutCustomer.vue'

const route = useRoute()

const castName = route.query.cast_name || ''
const courseName = route.query.course_name || ''
const date = route.query.date || ''
const time = route.query.time || ''
const total = route.query.total || 0
const storeQ = route.query.store ? '?store=' + route.query.store : ''

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}
</script>

<template>
  <LayoutCustomer>
    <div class="customer-submitted">

      <!-- 成功アイコン -->
      <div class="my-5">
        <div class="d-flex align-items-center justify-content-center rounded-circle mx-auto text-white fs-1" style="width: 80px; height: 80px; background: var(--color-success);">
          <i class="ti ti-check"></i>
        </div>
      </div>

      <h1 class="fs-3 mb-3 fw-bold">予約申請を受け付けました</h1>
      <p class="text-muted mb-4">
        ご予約ありがとうございます。内容を確認の上、承認結果をSMSでお知らせします。
      </p>

      <!-- 申請内容 -->
      <div class="card text-start">
        <div class="card-header">申請内容</div>
        <div class="card-body">
          <div class="list-group list-group-flush">
            <div class="list-group-item d-flex align-items-start flex-column gap-3">
              <div class="wrap">
                <div class="icon"><i class="ti ti-user"></i>担当</div>
                <div class="name">{{ castName }}</div>
              </div>
              <div class="wrap">
                <div class="icon"><i class="ti ti-calendar-event"></i>予約日時</div>
                <div class="text-muted">{{ date }} {{ time }}</div>
              </div>
              <div class="wrap">
                <div class="icon"><i class="ti ti-clock"></i>コース</div>
                <div class="text-muted">{{ courseName }}</div>
              </div>
              <div class="wrap">
                <div class="icon"><i class="ti ti-credit-card"></i>料金</div>
                <div><strong>{{ formatYen(total) }}</strong></div>
              </div>
              <div class="wrap">
                <div class="icon"><i class="ti ti-loader"></i>ステータス</div>
                <div><span class="badge badge-pending">申請中</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 次のステップ -->
      <div class="text-center p-3 mb-4">
        <strong class="mb-3 d-block">次のステップ</strong>
        <ul>
          <li>1.運営が内容を確認します<br>（通常30分～2時間程度）</li>
          <li class="text-center"><i class="ti ti-arrow-down-bar"></i></li>
          <li>2.承認された場合<br>SMSで通知をお送りします</li>
          <li class="text-center"><i class="ti ti-arrow-down-bar"></i></li>
          <li>3.SMSに記載されたURLから<br>予約詳細を確認できます</li>
        </ul>
      </div>

      <!-- SMS通知 -->
      <div class="card text-start">
        <div class="card-header">SMS通知について</div>
        <div class="card-body">
          <p class="mb-2">
            <i class="ti ti-message"></i> 登録電話番号にSMSで通知をお送りします。
          </p>
          <hr>
          <small class="text-muted">
            SMSが届かない場合は、お手数ですが店舗までお電話ください。<br>
            電話: 03-1234-5678（営業時間: 12:00-22:00）
          </small>
        </div>
      </div>

      <!-- アクション -->
      <div class="d-flex gap-3 justify-content-center mt-4 mb-5">
        <a :href="'/cu/mypage' + storeQ" class="btn btn-primary">
          <i class="ti ti-home"></i> マイページへ
        </a>
        <a :href="'/cu/booking' + storeQ" class="btn btn-outline-primary">
          <i class="ti ti-plus"></i> 別の予約を申請
        </a>
      </div>

      <!-- サポート情報 -->
      <div class="text-center text-muted small">
        <p>困ったことがあれば<br>いつでもお気軽にお問い合わせください。</p>
        <p class="mb-0">
          <i class="ti ti-phone"></i> 03-1234-5678<br>
          <i class="ti ti-mail"></i> support@roomink.example.com
        </p>
      </div>
    </div>
  </LayoutCustomer>
</template>
