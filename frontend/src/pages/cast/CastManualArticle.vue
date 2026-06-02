<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import LayoutCast from '../../components/LayoutCast.vue'
import ManualArticleBody from '../../components/manual/ManualArticleBody.vue'
import { findArticle, canReadArticle } from '../op/manualData.js'

const route = useRoute()
// キャスト画面なので cast 権限で閲覧可否を判定（cast向け記事のみ表示）
const found = computed(() => findArticle(route.params.slug))
const article = computed(() => (canReadArticle(found.value, 'cast') ? found.value : null))
const noPermission = computed(() => !!found.value && !canReadArticle(found.value, 'cast'))
</script>

<template>
  <LayoutCast>
    <div class="mb-3">
      <router-link to="/cast/manual" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> マニュアル一覧に戻る
      </router-link>
    </div>

    <!-- 閲覧権限がない場合 -->
    <div v-if="noPermission" class="alert alert-warning">
      この記事は表示できません。
    </div>

    <!-- 記事が見つからない場合 -->
    <div v-else-if="!article" class="alert alert-warning">
      指定された記事が見つかりません。
    </div>

    <!-- 記事本文 -->
    <div v-else class="card">
      <div class="card-header d-flex align-items-center gap-2">
        <span v-if="article.category" class="badge bg-warning text-dark">{{ article.category }}</span>
        <span class="fw-bold">{{ article.title }}</span>
      </div>
      <div class="card-body">
        <ManualArticleBody :article="article" />
      </div>
    </div>
  </LayoutCast>
</template>
