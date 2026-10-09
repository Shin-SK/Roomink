<script setup>
import { computed } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { getAuthIsOperationGroupManager, getAuthIsSuperuser, getAuthRole } from '../../router.js'

const isManager = computed(() => getAuthRole() === 'manager')
const isSuperuser = computed(() => getAuthIsSuperuser())
const isOperationGroupManager = computed(() => getAuthIsOperationGroupManager())

const menuItems = [
  { to: '/op/settings/setup', icon: 'ti-rocket', label: '初期設定', desc: '開業前に必要な設定を順番に進める', superuserOnly: true },
  { to: '/op/settings/casts', icon: 'ti-users', label: 'キャスト管理', desc: 'キャストの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/staffs', icon: 'ti-user-shield', label: 'スタッフ管理', desc: 'スタッフの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/operation-group', icon: 'ti-building-community', label: '運営管理', desc: '同じ契約内の店舗とスタッフの所属設定', operationGroupManagerOnly: true },
  { to: '/op/settings/work-devices', icon: 'ti-device-mobile', label: 'Roomink Work端末', desc: '受信端末の連携・受付停止・遠隔失効', operationGroupManagerOnly: true },
  { to: '/op/settings/rooms', icon: 'ti-door', label: 'ルーム管理', desc: 'ルームの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/courses', icon: 'ti-list', label: 'コース管理', desc: 'コースの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/options', icon: 'ti-puzzle', label: 'オプション管理', desc: 'オプションの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/extensions', icon: 'ti-clock-plus', label: '延長管理', desc: '延長の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/nomination-fees', icon: 'ti-star', label: '指名料管理', desc: '指名料の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/discounts', icon: 'ti-discount', label: '割引管理', desc: '割引の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/media', icon: 'ti-antenna', label: '媒体管理', desc: '媒体の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/csv-import', icon: 'ti-file-import', label: 'CSVインポート', desc: 'CSVファイルから一括登録', managerOnly: true },
  { to: '/op/settings/payment-fees', icon: 'ti-percentage', label: '決済手数料設定', desc: '現金/PayPay/カードの手数料率（参考値・マネージャーのみ）', managerOnly: true },
  { to: '/op/settings/business-day', icon: 'ti-calendar-time', label: '営業日・タイムライン設定', desc: '日付が切り替わる時刻を店舗ごとに設定', managerOnly: true },
  { to: '/op/settings/sms-templates', icon: 'ti-message', label: 'SMS文面設定', desc: '予約確認・カード決済前後のSMS文面と決済URL', managerOnly: false },
  { to: '/op/settings/public-booking', icon: 'ti-world-www', label: 'Web予約設定', desc: '店舗専用URLと予約画面の注意事項', managerOnly: true },
  { to: '/op/settings/line-activation', icon: 'ti-brand-line', label: 'LINE連携開始', desc: '準備完了後、店舗のタイミングで利用を開始', managerOnly: true },
  { to: '/op/settings/phones', icon: 'ti-phone', label: '電話・受付端末設定', desc: 'Roomink運営専用', superuserOnly: true },
  { to: '/op/settings/line', icon: 'ti-brand-line', label: '店舗LINE設定', desc: 'Roomink運営専用・選択中の店舗', superuserOnly: true },
  { to: '/op/settings/manual', icon: 'ti-book', label: '操作マニュアル', desc: 'Roominkの使い方ガイド' },
]

const visibleItems = computed(() =>
  menuItems.filter((item) =>
    (!item.managerOnly || isManager.value || isSuperuser.value) &&
    (!item.superuserOnly || isSuperuser.value) &&
    (!item.operationGroupManagerOnly || isOperationGroupManager.value || isSuperuser.value)
  )
)
</script>

<template>
  <LayoutOperator>
    <template #title>設定</template>

    <div class="settings-list">
      <router-link
        v-for="item in visibleItems"
        :key="item.to"
        :to="item.to"
        class="settings-item"
      >
        <i class="ti" :class="item.icon"></i>
        <div>
          <div class="settings-item__label">{{ item.label }}</div>
          <small class="text-muted">{{ item.desc }}</small>
        </div>
        <i class="ti ti-chevron-right ms-auto"></i>
      </router-link>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.settings-list {
  display: flex;
  flex-direction: column;
}
.settings-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 0;
  border-bottom: 1px solid #f0f0f0;
  text-decoration: none;
  color: inherit;
  transition: background 0.1s;
}
.settings-item:hover {
  background: #f9f9f9;
}
.settings-item .ti:first-child {
  font-size: 1.25rem;
  color: var(--rk-primary, #2A9D8F);
  width: 28px;
  text-align: center;
}
.settings-item__label {
  font-weight: 600;
  font-size: 0.95rem;
}
</style>
