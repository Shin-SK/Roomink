<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { findArticle } from './manualData.js'

const route = useRoute()
const article = computed(() => findArticle(route.params.slug))
</script>

<template>
  <LayoutOperator>
    <template #title>操作マニュアル</template>

    <div class="mb-3">
      <router-link to="/op/settings/manual" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> マニュアル一覧に戻る
      </router-link>
    </div>

    <!-- 記事が見つからない場合 -->
    <div v-if="!article" class="alert alert-warning">
      指定された記事が見つかりません。
    </div>

    <!-- 記事本文 -->
    <div v-else class="card">
      <div class="card-header d-flex align-items-center gap-2">
        <span v-if="article.category" class="badge bg-warning text-dark">{{ article.category }}</span>
        <span class="fw-bold">{{ article.title }}</span>
      </div>
      <div class="card-body article-body">

        <!-- 対象ユーザー -->
        <div class="article-section">
          <div class="article-label">対象ユーザー</div>
          <div>{{ article.target }}</div>
        </div>

        <!-- 開く画面 -->
        <div class="article-section">
          <div class="article-label">開く画面</div>
          <div class="screen-links">
            <router-link
              v-for="s in article.screens"
              :key="s.label"
              :to="s.path || '/op/settings/manual'"
              class="screen-link"
              :class="{ 'screen-link--disabled': !s.path }"
            >
              <i class="ti" :class="s.path ? 'ti-external-link' : 'ti-info-circle'"></i>
              {{ s.label }}
            </router-link>
          </div>
        </div>

        <!-- 手順（単一） -->
        <div v-if="article.steps && !article.stepsMulti" class="article-section">
          <div class="article-label">手順</div>
          <ol class="mb-0">
            <li v-for="s in article.steps" :key="s">{{ s }}</li>
          </ol>
        </div>

        <!-- 手順（複数ロール） -->
        <div v-if="article.stepsMulti" class="article-section">
          <div v-for="group in article.stepsMulti" :key="group.label" class="mb-3">
            <div class="article-label">手順（{{ group.label }}）</div>
            <ol class="mb-0">
              <li v-for="s in group.steps" :key="s">{{ s }}</li>
            </ol>
          </div>
        </div>

        <!-- 確認ポイント -->
        <div class="article-section">
          <div class="article-label">確認ポイント</div>
          <ul class="mb-0">
            <li v-for="c in article.confirm" :key="c">{{ c }}</li>
          </ul>
        </div>

        <!-- 注意点 -->
        <div class="article-section article-section--notes">
          <div class="article-label">注意点</div>
          <ul class="mb-0">
            <li v-for="n in article.notes" :key="n">{{ n }}</li>
          </ul>
        </div>

      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.article-body {
  font-size: 0.9rem;
  line-height: 1.7;
}
.article-section {
  margin-bottom: 1.25rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #f0f0f0;
}
.article-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}
.article-label {
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--rk-primary, #2A9D8F);
  margin-bottom: 0.35rem;
}
.article-section ul,
.article-section ol {
  padding-left: 1.25rem;
}
.article-section li {
  margin-bottom: 0.2rem;
}
.article-section--notes {
  background: #fffbf0;
  border: 1px solid #f0e6c8;
  border-radius: 6px;
  padding: 0.75rem 1rem;
}
.article-section--notes .article-label {
  color: #e67e22;
}
.screen-links {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.screen-link {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.75rem;
  background: #f0faf8;
  border: 1px solid #d0ece7;
  border-radius: 6px;
  color: var(--rk-primary, #2A9D8F);
  text-decoration: none;
  font-weight: 600;
  font-size: 0.9rem;
  transition: background 0.15s;
}
.screen-link:hover {
  background: #d0ece7;
}
.screen-link--disabled {
  background: #f5f5f5;
  border-color: #e0e0e0;
  color: #888;
  pointer-events: none;
}
</style>
