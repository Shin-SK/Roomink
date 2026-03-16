<script setup>
import LayoutOperator from '../../components/LayoutOperator.vue'

const menuItems = [
  { to: '/op/settings/casts', icon: 'ti-users', label: 'キャスト管理', desc: 'キャストの追加・編集・削除' },
  { to: '/op/settings/rooms', icon: 'ti-door', label: 'ルーム管理', desc: 'ルームの追加・編集・削除' },
  { to: '/op/settings/courses', icon: 'ti-list', label: 'コース管理', desc: 'コースの追加・編集・削除' },
  { to: '/op/settings/options', icon: 'ti-puzzle', label: 'オプション管理', desc: 'オプションの追加・編集・削除' },
  { to: '/op/settings/extensions', icon: 'ti-clock-plus', label: '延長管理', desc: '延長の追加・編集・削除' },
  { to: '/op/settings/nomination-fees', icon: 'ti-star', label: '指名料管理', desc: '指名料の追加・編集・削除' },
  { to: '/op/settings/discounts', icon: 'ti-discount', label: '割引管理', desc: '割引の追加・編集・削除' },
  { to: '/op/settings/media', icon: 'ti-antenna', label: '媒体管理', desc: '媒体の追加・編集・削除' },
]
</script>

<template>
  <LayoutOperator>
    <template #title>設定</template>

    <div class="row g-3">
      <div v-for="item in menuItems" :key="item.to" class="col-12 col-sm-6 col-md-4">
        <router-link :to="item.to" class="card text-decoration-none h-100">
          <div class="card-body d-flex align-items-center gap-3">
            <i class="ti fs-3" :class="item.icon"></i>
            <div>
              <h6 class="mb-1">{{ item.label }}</h6>
              <small class="text-muted">{{ item.desc }}</small>
            </div>
          </div>
        </router-link>
      </div>
    </div>
  </LayoutOperator>
</template>
