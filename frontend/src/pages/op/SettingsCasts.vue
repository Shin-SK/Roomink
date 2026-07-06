<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { uploadToCloudinary } from '../../cloudinary.js'

const loading = ref(true)
const error = ref('')
const casts = ref([])

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)
const uploading = ref(false)

function emptyForm() {
  return { name: '', avatar_url: '', age: '', hp_url: '', introduction: '', staff_memo: '', interval_minutes: 15, course_back_rate: 0, option_fullback_enabled: false }
}

async function loadCasts() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCasts()
    casts.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => loadCasts())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
  expenseTemplates.value = []
  showExpenseForm.value = false
  showExpenseHistory.value = false
  expenseHistory.value = []
}

function openEdit(c) {
  editingId.value = c.id
  form.value = {
    name: c.name,
    avatar_url: c.avatar_url || '',
    age: c.age ?? '',
    hp_url: c.hp_url || '',
    introduction: c.introduction || '',
    staff_memo: c.staff_memo || '',
    interval_minutes: c.interval_minutes ?? 15,
    course_back_rate: c.course_back_rate ?? 0,
    option_fullback_enabled: c.option_fullback_enabled ?? false,
  }
  formError.value = ''
  showForm.value = true
  showExpenseForm.value = false
  showExpenseHistory.value = false
  expenseHistory.value = []
  loadExpenseTemplates(c.id)
}

async function onAvatarChange(e) {
  const file = e.target.files[0]
  if (!file) return
  uploading.value = true
  formError.value = ''
  try {
    const url = await uploadToCloudinary(file)
    form.value.avatar_url = url
  } catch (e) {
    formError.value = e.message
  } finally {
    uploading.value = false
  }
}

const showAvatarMenu = ref(false)

function onAvatarTap() {
  if (form.value.avatar_url) {
    showAvatarMenu.value = true
  } else {
    document.getElementById('avatar-file').click()
  }
}

function avatarChooseNew() {
  showAvatarMenu.value = false
  document.getElementById('avatar-file').click()
}

function avatarRemove() {
  showAvatarMenu.value = false
  form.value.avatar_url = ''
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const payload = {
      name: form.value.name,
      avatar_url: form.value.avatar_url,
      age: form.value.age === '' ? null : Number(form.value.age),
      hp_url: form.value.hp_url,
      introduction: form.value.introduction,
      staff_memo: form.value.staff_memo,
      interval_minutes: Number(form.value.interval_minutes),
      course_back_rate: Number(form.value.course_back_rate),
      option_fullback_enabled: form.value.option_fullback_enabled,
    }
    if (editingId.value) {
      await api.updateCast(editingId.value, payload)
    } else {
      await api.createCast(payload)
    }
    showForm.value = false
    await loadCasts()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(c) {
  if (!confirm(`「${c.name}」を削除しますか？`)) return
  error.value = ''
  try {
    await api.deleteCast(c.id)
    await loadCasts()
  } catch (e) {
    error.value = e.message
  }
}

// 固定雑費テンプレ
const expenseTemplates = ref([])
const expenseTemplatesLoading = ref(false)
const expenseTemplatesError = ref('')
const showExpenseForm = ref(false)
const editingExpenseTemplateId = ref(null)
const expenseForm = ref(emptyExpenseForm())
const expenseSaving = ref(false)

function emptyExpenseForm() {
  return { name: '', amount: 0, memo: '' }
}

async function loadExpenseTemplates(castId) {
  expenseTemplatesLoading.value = true
  expenseTemplatesError.value = ''
  try {
    const data = await api.getCastExpenseTemplates(castId)
    expenseTemplates.value = Array.isArray(data) ? data : []
  } catch (e) {
    expenseTemplatesError.value = e.message
  } finally {
    expenseTemplatesLoading.value = false
  }
}

function openExpenseCreate() {
  editingExpenseTemplateId.value = null
  expenseForm.value = emptyExpenseForm()
  showExpenseForm.value = true
}

function openExpenseEdit(t) {
  editingExpenseTemplateId.value = t.id
  expenseForm.value = { name: t.name, amount: t.amount, memo: t.memo || '' }
  showExpenseForm.value = true
}

async function onExpenseSave() {
  expenseSaving.value = true
  expenseTemplatesError.value = ''
  try {
    const body = {
      name: expenseForm.value.name,
      amount: Number(expenseForm.value.amount),
      memo: expenseForm.value.memo,
    }
    if (editingExpenseTemplateId.value) {
      await api.updateCastExpenseTemplate(editingExpenseTemplateId.value, body)
    } else {
      await api.createCastExpenseTemplate({ ...body, cast: editingId.value })
    }
    showExpenseForm.value = false
    await loadExpenseTemplates(editingId.value)
  } catch (e) {
    expenseTemplatesError.value = e.message
  } finally {
    expenseSaving.value = false
  }
}

async function onExpenseToggleActive(t) {
  expenseTemplatesError.value = ''
  try {
    await api.setCastExpenseTemplateActive(t.id, !t.is_active)
    await loadExpenseTemplates(editingId.value)
  } catch (e) {
    expenseTemplatesError.value = e.message
  }
}

// 固定雑費テンプレ履歴
const showExpenseHistory = ref(false)
const expenseHistory = ref([])
const expenseHistoryLoading = ref(false)
const expenseHistoryError = ref('')

const expenseActionLabels = {
  CREATE: '作成',
  UPDATE: '更新',
  ACTIVATE: '有効化',
  DEACTIVATE: '無効化',
}

function expenseActionLabel(action) {
  return expenseActionLabels[action] || action
}

async function toggleExpenseHistory() {
  showExpenseHistory.value = !showExpenseHistory.value
  if (showExpenseHistory.value) {
    expenseHistoryLoading.value = true
    expenseHistoryError.value = ''
    try {
      const data = await api.getCastExpenseTemplateHistories(editingId.value)
      expenseHistory.value = Array.isArray(data) ? data : []
    } catch (e) {
      expenseHistoryError.value = e.message
    } finally {
      expenseHistoryLoading.value = false
    }
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>キャスト管理</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-users"></i> キャスト一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus text-white"></i> キャスト追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!casts.length" class="text-muted text-center py-3">
          キャストが登録されていません
        </div>

        <table v-else class="table table-hover mb-0 cast-table">
          <colgroup>
            <col style="width: 56px">
            <col style="width: 140px">
            <col>
            <col style="width: 64px">
            <col style="width: 64px">
            <col style="width: 72px">
            <col style="width: 80px">
            <col style="width: 48px">
          </colgroup>
          <thead>
            <tr>
              <th></th>
              <th>名前</th>
              <th>常時メモ</th>
              <th class="text-end">年齢</th>
              <th class="text-end">IV</th>
              <th class="text-end">バック</th>
              <th class="text-center">LINE</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in casts" :key="c.id">
              <td>
                <img
                  v-if="c.avatar_url"
                  :src="c.avatar_url"
                  :alt="c.name"
                  style="width: 36px; height: 36px; border-radius: 50%; object-fit: cover;"
                >
                <div
                  v-else
                  class="d-flex align-items-center justify-content-center bg-light"
                  style="width: 36px; height: 36px; border-radius: 50%; color: var(--rk-primary);"
                >
                  <i class="ti ti-user"></i>
                </div>
              </td>
              <td class="cast-name-cell">{{ c.name }}</td>
              <td class="cast-memo-cell">
                <button
                  v-if="c.staff_memo"
                  type="button"
                  class="cast-memo-text"
                  :title="c.staff_memo"
                  @click="openEdit(c)"
                >{{ c.staff_memo }}</button>
                <button
                  v-else
                  type="button"
                  class="cast-memo-empty"
                  @click="openEdit(c)"
                >＋ メモを追加</button>
              </td>
              <td class="text-end">{{ c.age || '—' }}</td>
              <td class="text-end">{{ c.interval_minutes }}分</td>
              <td class="text-end">{{ c.course_back_rate }}%</td>
              <td class="text-center">
                <span v-if="c.line_linked" class="badge bg-success">連携済</span>
                <span v-else class="badge bg-secondary">未連携</span>
              </td>
              <td class="text-end">
                <button class="btn btn-link p-0" @click="openEdit(c)">
                  <i class="ti ti-edit" style="font-size: 1.25rem;"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingId ? 'キャスト編集' : 'キャスト追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3 text-center position-relative">
              <div class="avatar-tap" @click="onAvatarTap" style="cursor: pointer; display: inline-block; position: relative;">
                <img
                  v-if="form.avatar_url"
                  :src="form.avatar_url"
                  alt="avatar"
                  style="width: 160px; height: 160px; border-radius: 50%; object-fit: cover;"
                >
                <div
                  v-else
                  class="d-inline-flex align-items-center justify-content-center bg-light"
                  style="width: 160px; height: 160px; border-radius: 50%; font-size: 64px; color: #ccc;"
                >
                  <i class="ti ti-user"></i>
                </div>
                <div class="avatar-overlay">
                  <i class="ti ti-camera"></i>
                </div>
              </div>
              <input
                id="avatar-file"
                type="file"
                accept="image/*"
                :disabled="uploading"
                @change="onAvatarChange"
                style="display: none;"
              />
              <small v-if="uploading" class="text-muted d-block mt-1">アップロード中...</small>

              <!-- アバターメニュー -->
              <div v-if="showAvatarMenu" class="avatar-menu-overlay" @click="showAvatarMenu = false">
                <div class="avatar-menu" @click.stop>
                  <button class="avatar-menu__item" @click="avatarChooseNew">
                    <i class="ti ti-photo"></i> 画像を変更する
                  </button>
                  <button class="avatar-menu__item text-danger" @click="avatarRemove">
                    <i class="ti ti-trash"></i> 画像を削除する
                  </button>
                  <button class="avatar-menu__item text-muted" @click="showAvatarMenu = false">
                    キャンセル
                  </button>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">名前 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" placeholder="キャスト名" />
            </div>
            <div class="mb-3">
              <label class="form-label">年齢</label>
              <input v-model="form.age" type="number" class="form-control" min="0" placeholder="未設定" />
            </div>
            <div class="mb-3">
              <label class="form-label">HP URL</label>
              <input v-model="form.hp_url" type="url" class="form-control" placeholder="https://..." />
            </div>
            <div class="mb-3">
              <label class="form-label">紹介コメント（お客様表示用）</label>
              <textarea v-model="form.introduction" class="form-control" rows="2" placeholder="お客様マイページに表示される紹介文"></textarea>
            </div>
            <div class="mb-3">
              <label class="form-label">運営専用メモ</label>
              <textarea v-model="form.staff_memo" class="form-control" rows="2" placeholder="運営のみが閲覧可能なメモ"></textarea>
            </div>

            <hr class="my-3">
            <h6 class="mb-3">運用設定</h6>
            <div class="mb-3">
              <label class="form-label">インターバル時間（分）</label>
              <input v-model.number="form.interval_minutes" type="number" class="form-control" min="0" step="5" />
              <small class="text-muted">予約と予約の間に確保する時間</small>
            </div>
            <div class="mb-3">
              <label class="form-label">コースバック率（%）</label>
              <input v-model.number="form.course_back_rate" type="number" class="form-control" min="0" max="100" />
            </div>
            <div class="mb-3 form-check">
              <input v-model="form.option_fullback_enabled" type="checkbox" class="form-check-input" id="optionFullback" />
              <label class="form-check-label" for="optionFullback">オプション全額バック</label>
            </div>

            <template v-if="editingId">
              <hr class="my-3">
              <div class="d-flex align-items-center justify-content-between mb-2">
                <h6 class="mb-0">固定雑費</h6>
                <div class="d-flex gap-2">
                  <button class="btn btn-outline-secondary btn-sm" @click="toggleExpenseHistory">
                    {{ showExpenseHistory ? '履歴を閉じる' : '履歴を見る' }}
                  </button>
                  <button class="btn btn-outline-primary btn-sm" @click="openExpenseCreate">
                    <i class="ti ti-plus"></i> 追加
                  </button>
                </div>
              </div>

              <div v-if="showExpenseHistory" class="border rounded p-2 mb-2 bg-light">
                <div v-if="expenseHistoryError" class="alert alert-danger py-1 px-2 small mb-2">{{ expenseHistoryError }}</div>
                <div v-if="expenseHistoryLoading" class="text-center py-2">
                  <div class="spinner-border spinner-border-sm text-primary"></div>
                </div>
                <div v-else-if="!expenseHistory.length" class="text-muted small py-1">
                  履歴はありません
                </div>
                <div v-else class="table-responsive">
                  <table class="table table-sm mb-0">
                    <thead>
                      <tr>
                        <th>日時</th>
                        <th>操作者</th>
                        <th>アクション</th>
                        <th>名称</th>
                        <th>金額</th>
                        <th>メモ</th>
                        <th>状態</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="h in expenseHistory" :key="h.id">
                        <td class="text-nowrap small">{{ new Date(h.edited_at).toLocaleString('ja-JP') }}</td>
                        <td class="small">{{ h.edited_by_name || '-' }}</td>
                        <td class="small">{{ expenseActionLabel(h.action) }}</td>
                        <td class="small">{{ h.name }}</td>
                        <td class="small">¥{{ h.amount }}</td>
                        <td class="small">{{ h.memo || '-' }}</td>
                        <td class="small">{{ h.is_active ? '有効' : '無効' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div v-if="expenseTemplatesError" class="alert alert-danger py-1 px-2 small">{{ expenseTemplatesError }}</div>

              <div v-if="expenseTemplatesLoading" class="text-center py-2">
                <div class="spinner-border spinner-border-sm text-primary"></div>
              </div>
              <div v-else-if="!expenseTemplates.length" class="text-muted small py-1">
                固定雑費は登録されていません
              </div>
              <ul v-else class="list-group mb-0">
                <li
                  v-for="t in expenseTemplates"
                  :key="t.id"
                  class="list-group-item d-flex align-items-center justify-content-between"
                  :class="{ 'expense-inactive': !t.is_active }"
                >
                  <div class="flex-grow-1">
                    <div>
                      <strong>{{ t.name }}</strong> ¥{{ t.amount }}
                      <span v-if="!t.is_active" class="badge bg-secondary ms-1">無効</span>
                    </div>
                    <div v-if="t.memo" class="text-muted small">{{ t.memo }}</div>
                  </div>
                  <div class="text-nowrap">
                    <button class="btn btn-link btn-sm p-1" @click="openExpenseEdit(t)">
                      <i class="ti ti-edit"></i>
                    </button>
                    <button
                      class="btn btn-link btn-sm p-1"
                      :class="t.is_active ? 'text-danger' : 'text-success'"
                      @click="onExpenseToggleActive(t)"
                    >
                      {{ t.is_active ? '無効化' : '有効化' }}
                    </button>
                  </div>
                </li>
              </ul>

              <!-- 固定雑費 追加/編集フォーム -->
              <div v-if="showExpenseForm" class="border rounded p-2 mt-2">
                <div class="mb-2">
                  <label class="form-label small mb-1">名称</label>
                  <input v-model="expenseForm.name" type="text" class="form-control form-control-sm" placeholder="例: 雑費" />
                </div>
                <div class="mb-2">
                  <label class="form-label small mb-1">金額</label>
                  <input v-model.number="expenseForm.amount" type="number" class="form-control form-control-sm" min="0" />
                </div>
                <div class="mb-2">
                  <label class="form-label small mb-1">メモ</label>
                  <input v-model="expenseForm.memo" type="text" class="form-control form-control-sm" placeholder="任意" />
                </div>
                <div class="d-flex justify-content-end gap-2">
                  <button class="btn btn-secondary btn-sm" @click="showExpenseForm = false">キャンセル</button>
                  <button
                    class="btn btn-primary btn-sm"
                    :disabled="expenseSaving || !expenseForm.name.trim()"
                    @click="onExpenseSave"
                  >
                    {{ expenseSaving ? '保存中...' : '保存' }}
                  </button>
                </div>
              </div>
            </template>
          </div>
          <div class="modal-footer d-flex">
            <button v-if="editingId" class="btn btn-outline-danger me-auto" @click="onDelete({ id: editingId, name: form.name })">
              <i class="ti ti-trash"></i> 削除
            </button>
            <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
            <button class="btn btn-primary" :disabled="saving || uploading || !form.name.trim()" @click="onSave">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.avatar-overlay {
  position: absolute;
  bottom: 4px;
  right: 4px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--rk-primary, #2A9D8F);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.avatar-menu-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.3);
  z-index: 1060;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.avatar-menu {
  background: #fff;
  border-radius: 12px 12px 0 0;
  width: 100%;
  max-width: 400px;
  padding: 0.5rem 0;
}

.avatar-menu__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.875rem 1.25rem;
  border: none;
  background: none;
  font-size: 1rem;
  text-align: left;
  cursor: pointer;
}

.avatar-menu__item:hover {
  background: #f5f5f5;
}

.cast-table {
  table-layout: fixed;
  width: 100%;
}
.cast-table th,
.cast-table td {
  vertical-align: middle;
}

.cast-name-cell {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cast-memo-cell {
  overflow: hidden;
}

.cast-memo-text {
  display: block;
  width: 100%;
  max-width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  color: #334155;
  font-size: 0.9rem;
  padding: 4px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
  line-height: 1.4;
}
.cast-memo-text:hover {
  color: var(--rk-primary);
  text-decoration: underline;
}

.cast-memo-empty {
  border: 1px dashed #cbd5e1;
  background: transparent;
  color: #94a3b8;
  font-size: 0.8rem;
  padding: 3px 10px;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
}
.cast-memo-empty:hover {
  background: #f8fafc;
  color: #64748b;
}

.expense-inactive {
  opacity: 0.55;
}
</style>
