<script setup>
import LayoutCast from '../../components/LayoutCast.vue'
import { articlesForRole, MANUAL_CATEGORIES } from '../op/manualData.js'

// キャスト本人向け（roles に cast を含む）記事だけ表示
const articles = articlesForRole('cast')

const groups = MANUAL_CATEGORIES
  .map(cat => ({ category: cat, items: articles.filter(a => a.category === cat) }))
  .filter(g => g.items.length > 0)

const others = articles.filter(a => !MANUAL_CATEGORIES.includes(a.category))
if (others.length) groups.push({ category: 'その他', items: others })
</script>

<template>
  <LayoutCast>
    <h1 class="page-title mb-3">マニュアル</h1>

    <div v-if="!groups.length" class="alert alert-info">
      表示できるマニュアルはまだありません。
    </div>

    <div v-for="g in groups" :key="g.category" class="card mb-4">
      <div class="card-header">
        <i class="ti" :class="g.category === 'トラブル' ? 'ti-alert-triangle' : 'ti-book'"></i>
        {{ g.category }}
      </div>
      <div class="card-body p-0">
        <router-link
          v-for="(a, i) in g.items"
          :key="a.slug"
          :to="`/cast/manual/${a.slug}`"
          class="manual-item"
        >
          <span
            class="manual-item__num"
            :class="{ 'manual-item__num--trouble': g.category === 'トラブル' }"
          >{{ g.category === 'トラブル' ? '?' : i + 1 }}</span>
          <div class="manual-item__body">
            <div class="manual-item__title">{{ a.title }}</div>
            <small class="text-muted d-block">{{ a.summary || a.target }}</small>
          </div>
          <i class="ti ti-chevron-right ms-auto"></i>
        </router-link>
      </div>
    </div>
  </LayoutCast>
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
