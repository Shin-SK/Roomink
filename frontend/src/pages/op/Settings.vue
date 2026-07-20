<script setup>
import { computed } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { getAuthRole } from '../../router.js'

const isManager = computed(() => getAuthRole() === 'manager')

const menuItems = [
  { to: '/op/settings/casts', icon: 'ti-users', label: 'キャスト管理', desc: 'キャストの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/staffs', icon: 'ti-user-shield', label: 'スタッフ管理', desc: 'スタッフの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/rooms', icon: 'ti-door', label: 'ルーム管理', desc: 'ルームの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/courses', icon: 'ti-list', label: 'コース管理', desc: 'コースの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/options', icon: 'ti-puzzle', label: 'オプション管理', desc: 'オプションの追加・編集・削除', managerOnly: true },
  { to: '/op/settings/extensions', icon: 'ti-clock-plus', label: '延長管理', desc: '延長の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/nomination-fees', icon: 'ti-star', label: '指名料管理', desc: '指名料の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/discounts', icon: 'ti-discount', label: '割引管理', desc: '割引の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/media', icon: 'ti-antenna', label: '媒体管理', desc: '媒体の追加・編集・削除', managerOnly: true },
  { to: '/op/settings/csv-import', icon: 'ti-file-import', label: 'CSVインポート', desc: 'CSVファイルから一括登録', managerOnly: true },
  { to: '/op/settings/line', icon: 'ti-brand-line', label: 'LINE連携設定', desc: 'Webhook・Channel設定（マネージャーのみ）', managerOnly: true },
  { to: '/op/settings/payment-fees', icon: 'ti-percentage', label: '決済手数料設定', desc: '現金/PayPay/カードの手数料率（参考値・マネージャーのみ）', managerOnly: true },
  { to: '/op/settings/sms-templates', icon: 'ti-message', label: 'SMS文面設定', desc: '会計方法（現金/カード/PayPay/未設定）ごとの予約確認SMS文面', managerOnly: false },
  { to: '/op/settings/phones', icon: 'ti-phone', label: 'CTI電話番号設定', desc: 'CTI着信番号の登録・編集', managerOnly: true },
  { to: '/op/settings/manual', icon: 'ti-book', label: '操作マニュアル', desc: 'Roominkの使い方ガイド' },
]

const visibleItems = computed(() =>
  menuItems.filter((item) => !item.managerOnly || isManager.value)
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
