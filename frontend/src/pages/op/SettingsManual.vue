<script setup>
import LayoutOperator from '../../components/LayoutOperator.vue'
import { manualArticles } from './manualData.js'

const operations = manualArticles.filter(a => !a.category)
const troubles = manualArticles.filter(a => a.category === 'トラブル')
</script>

<template>
  <LayoutOperator>
    <template #title>操作マニュアル</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <!-- 操作ガイド -->
    <div class="card mb-4">
      <div class="card-header">
        <i class="ti ti-book"></i> やりたいことから探す
      </div>
      <div class="card-body p-0">
        <router-link
          v-for="(a, i) in operations"
          :key="a.slug"
          :to="`/op/settings/manual/${a.slug}`"
          class="manual-item"
        >
          <span class="manual-item__num">{{ i + 1 }}</span>
          <div class="manual-item__body">
            <div class="manual-item__title">{{ a.title }}</div>
            <small class="text-muted">{{ a.target }}</small>
          </div>
          <i class="ti ti-chevron-right ms-auto"></i>
        </router-link>
      </div>
    </div>

    <!-- トラブルシューティング -->
    <div class="card">
      <div class="card-header">
        <i class="ti ti-alert-triangle"></i> よくあるトラブル
      </div>
      <div class="card-body p-0">
        <router-link
          v-for="a in troubles"
          :key="a.slug"
          :to="`/op/settings/manual/${a.slug}`"
          class="manual-item"
        >
          <span class="manual-item__num manual-item__num--trouble">?</span>
          <div class="manual-item__body">
            <div class="manual-item__title">{{ a.title }}</div>
            <small class="text-muted">{{ a.target }}</small>
          </div>
          <i class="ti ti-chevron-right ms-auto"></i>
        </router-link>
      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.manual-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f0f0f0;
  text-decoration: none;
  color: inherit;
  transition: background 0.1s;
}
.manual-item:last-child {
  border-bottom: none;
}
.manual-item:hover {
  background: #f9f9f9;
}
.manual-item__num {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--rk-primary, #2A9D8F);
  color: #fff;
  font-size: 0.8rem;
  font-weight: 700;
  flex-shrink: 0;
}
.manual-item__num--trouble {
  background: #e67e22;
}
.manual-item__body {
  min-width: 0;
}
.manual-item__title {
  font-weight: 600;
  font-size: 0.95rem;
}
</style>
