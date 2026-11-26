<template>
  <section class="panel" data-testid="sku-sync-panel">
    <h3 class="panel-title">规格同步候选与确认</h3>
    <p class="panel-desc">
      候选规格实际取自规格同步数据；写确认后归一器可重开页面查看那次生效及其规格来源。
    </p>

    <h4 class="panel-subtitle">同步候选（来自规格同步数据）</h4>
    <table class="data-table" data-testid="sync-candidate-table">
      <thead>
        <tr>
          <th>同步批次</th>
          <th>商品标识</th>
          <th>候选规格（同步快照）</th>
          <th>规则版本</th>
          <th>同步状态</th>
          <th>匹配单状态</th>
          <th>撤回原因</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in candidates" :key="item.同步批次ID" :data-testid="`candidate-${item.同步批次ID}`">
          <td>{{ item.同步批次 }}</td>
          <td>{{ item.商品标识 }}</td>
          <td>{{ item.候选规格 }}</td>
          <td>{{ item.规则版本 }}</td>
          <td>{{ item.同步状态 }}</td>
          <td>{{ item.匹配单状态 || '—' }}</td>
          <td>{{ item.撤回原因 || '—' }}</td>
          <td class="row-actions">
            <button
              v-if="item.同步状态 === '待匹配'"
              class="link"
              type="button"
              :data-testid="`start-${item.同步批次ID}`"
              @click="doStart(item)"
            >
              开始匹配
            </button>
            <button
              v-if="item.同步状态 === '匹配中'"
              class="link"
              type="button"
              :data-testid="`confirm-${item.同步批次ID}`"
              @click="doConfirm(item)"
            >
              写确认
            </button>
            <template v-if="item.同步状态 === '撤回中'">
              <button
                class="link"
                type="button"
                :data-testid="`finish-old-${item.同步批次ID}`"
                @click="doResolve(item, 'finish_old')"
              >
                用旧版处理完
              </button>
              <button
                class="link"
                type="button"
                :data-testid="`redo-new-${item.同步批次ID}`"
                @click="doResolve(item, 'redo_new')"
              >
                需用新版重做
              </button>
            </template>
          </td>
        </tr>
        <tr v-if="!candidates.length">
          <td colspan="8" class="empty-state">暂无待处理的同步候选</td>
        </tr>
      </tbody>
    </table>

    <h4 class="panel-subtitle">规格交接回执（判断旧同步成果是否仍能使用）</h4>
    <SpecReceiptTable :items="receipts" />

    <h4 class="panel-subtitle">已确认历史回查（资格与版本）</h4>
    <form class="filter-bar" @submit.prevent="loadConfirmed">
      <label class="filter-item">
        <span>同步批次 / 商品标识</span>
        <input v-model="confirmedKeyword" data-testid="confirmed-keyword" placeholder="如 K4" />
      </label>
      <button class="btn" data-testid="confirmed-query" type="submit">查询</button>
    </form>
    <table class="data-table" data-testid="confirmed-table">
      <thead>
        <tr>
          <th>同步批次</th>
          <th>商品标识</th>
          <th>归一规格</th>
          <th>规则版本</th>
          <th>资格</th>
          <th>匹配单状态</th>
          <th>确认时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in confirmed" :key="item.同步批次" :data-testid="`confirmed-${item.同步批次}`">
          <td>{{ item.同步批次 }}</td>
          <td>{{ item.商品标识 }}</td>
          <td>{{ item.归一规格 }}</td>
          <td>{{ item.规则版本 }}</td>
          <td>{{ item.资格 }}</td>
          <td>{{ item.匹配单状态 }}</td>
          <td>{{ fmtTime(item.确认时间) }}</td>
        </tr>
        <tr v-if="!confirmed.length">
          <td colspan="7" class="empty-state">暂无已确认的同步记录</td>
        </tr>
      </tbody>
    </table>

    <p v-if="message" class="panel-message" data-testid="sku-sync-message">{{ message }}</p>
    <p v-if="error" class="error-text" data-testid="sku-sync-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import SpecReceiptTable from '@/views/SpecReceiptTable.vue'
import {
  confirmMatch,
  fetchCandidates,
  fetchConfirmed,
  fetchReceipts,
  fmtTime,
  resolveWithdrawal,
  startMatch,
  type ConfirmedSync,
  type SyncCandidate,
  type SyncReceipt,
} from '@/api/spec-sync'

const emit = defineEmits<{ changed: [] }>()

const candidates = ref<SyncCandidate[]>([])
const receipts = ref<SyncReceipt[]>([])
const confirmed = ref<ConfirmedSync[]>([])
const confirmedKeyword = ref('')
const message = ref('')
const error = ref('')

function report(result: { ok: boolean; message?: string }) {
  if (result.ok) {
    message.value = result.message ?? '操作完成'
    error.value = ''
  } else {
    error.value = result.message ?? '操作失败'
    message.value = ''
  }
}

async function loadCandidates() {
  const payload = await fetchCandidates()
  candidates.value = payload.items
}

async function loadReceipts() {
  const payload = await fetchReceipts()
  receipts.value = payload.items
}

async function loadConfirmed() {
  const payload = await fetchConfirmed(confirmedKeyword.value.trim())
  confirmed.value = payload.items
}

async function reloadAll() {
  await Promise.all([loadCandidates(), loadReceipts(), loadConfirmed()])
}

async function doStart(item: SyncCandidate) {
  const result = await startMatch(item.同步批次ID)
  report(result)
  await reloadAll()
  emit('changed')
}

async function doConfirm(item: SyncCandidate) {
  const result = await confirmMatch(item.同步批次ID)
  report(result)
  await reloadAll()
  emit('changed')
}

async function doResolve(item: SyncCandidate, mode: 'finish_old' | 'redo_new') {
  const result = await resolveWithdrawal(item.同步批次ID, mode)
  report(result)
  await reloadAll()
  emit('changed')
}

onMounted(async () => {
  try {
    await reloadAll()
  } catch {
    error.value = '规格同步候选读取失败'
  }
})
</script>
