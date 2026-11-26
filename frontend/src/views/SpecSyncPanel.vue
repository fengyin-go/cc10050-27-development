<template>
  <section class="panel" data-testid="spec-sync-panel">
    <h3 class="panel-title">规格同步批次核对</h3>
    <p class="panel-desc">
      核对已启用归一规格与同步批次；同步记录锁定商品、规格快照与规则实用版本，不按名称现查替代原规则。
    </p>

    <h4 class="panel-subtitle">已启用归一规格</h4>
    <table class="data-table" data-testid="enabled-rule-table">
      <thead>
        <tr>
          <th>规则名称</th>
          <th>规则版本</th>
          <th>源规格文本</th>
          <th>归一规格</th>
          <th>单位换算</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="rule in enabledRules" :key="rule.id" :data-testid="`enabled-rule-${rule.id}`">
          <td>{{ rule.规则名称 }}</td>
          <td>{{ rule.规则版本 }}</td>
          <td>{{ rule.源规格文本 }}</td>
          <td>{{ rule.归一规格 }}</td>
          <td>{{ rule.单位换算 || '—' }}</td>
          <td class="row-actions">
            <button
              class="link"
              type="button"
              :data-testid="`correct-rule-${rule.id}`"
              @click="openCorrect(rule)"
            >
              更正规则
            </button>
          </td>
        </tr>
        <tr v-if="!enabledRules.length">
          <td colspan="6" class="empty-state">暂无已启用规则</td>
        </tr>
      </tbody>
    </table>

    <h4 class="panel-subtitle">同步批次（可查询原批次并申请同步撤回）</h4>
    <form class="filter-bar" @submit.prevent="loadBatches">
      <label class="filter-item">
        <span>原批次号 / 商品标识</span>
        <input v-model="batchKeyword" data-testid="sync-batch-keyword" placeholder="如 SYNC-R419-K5" />
      </label>
      <label class="filter-item">
        <span>同步状态</span>
        <select v-model="batchStatus" data-testid="sync-batch-status">
          <option value="">全部</option>
          <option v-for="state in SYNC_STATUSES" :key="state" :value="state">{{ state }}</option>
        </select>
      </label>
      <button class="btn" data-testid="sync-batch-query" type="submit">查询</button>
    </form>
    <table class="data-table" data-testid="sync-batch-table">
      <thead>
        <tr>
          <th>同步批次</th>
          <th>商品标识</th>
          <th>归一规格（快照）</th>
          <th>规则版本</th>
          <th>匹配批次</th>
          <th>同步状态</th>
          <th>撤回原因</th>
          <th>确认时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="batch in batches" :key="batch.id" :data-testid="`sync-batch-${batch.id}`">
          <td>{{ batch.同步批次 }}</td>
          <td>{{ batch.商品标识 }}</td>
          <td>{{ batch.归一规格 }}</td>
          <td>{{ batch.规则版本 }}</td>
          <td>{{ batch.匹配批次 }}</td>
          <td>{{ batch.同步状态 }}</td>
          <td>{{ batch.撤回原因 || '—' }}</td>
          <td>{{ fmtTime(batch.确认时间) }}</td>
          <td class="row-actions">
            <button
              v-if="canContinue(batch)"
              class="link"
              type="button"
              :data-testid="`continue-${batch.id}`"
              @click="doContinue(batch)"
            >
              继续原同步
            </button>
            <button
              v-if="canWithdraw(batch)"
              class="link"
              type="button"
              :data-testid="`withdraw-${batch.id}`"
              @click="openWithdraw(batch)"
            >
              申请撤回
            </button>
            <button
              class="link"
              type="button"
              :data-testid="`view-receipt-${batch.id}`"
              @click="viewReceipt(batch)"
            >
              查看回执
            </button>
          </td>
        </tr>
        <tr v-if="!batches.length">
          <td colspan="9" class="empty-state">暂无同步批次，可在下方发起规格同步</td>
        </tr>
      </tbody>
    </table>

    <form class="analysis-form" data-testid="submit-sync-form" @submit.prevent="submitNewSync">
      <label>
        <span>发起同步：归一规则</span>
        <select v-model.number="submitRuleId" data-testid="submit-sync-rule">
          <option v-for="rule in enabledRules" :key="rule.id" :value="rule.id">
            {{ rule.规则名称 }}（{{ rule.规则版本 }} · {{ rule.归一规格 }}）
          </option>
        </select>
      </label>
      <label>
        <span>商品标识</span>
        <input v-model="submitGoods" data-testid="submit-sync-goods" placeholder="如 K6" />
      </label>
      <button class="btn primary" data-testid="submit-sync" type="submit" :disabled="submitting">
        {{ submitting ? '提交中…' : '发起规格同步' }}
      </button>
    </form>

    <h4 class="panel-subtitle">规格交接回执（匹配方实际处理了哪一批、撤回还需做什么）</h4>
    <SpecReceiptTable :items="receipts" />

    <div v-if="correctTarget" class="modal-backdrop" data-testid="correct-modal">
      <form class="modal" @submit.prevent="submitCorrect">
        <h3>更正规则 {{ correctTarget.规则名称 }}</h3>
        <p class="panel-desc">
          当前 {{ correctTarget.规则版本 }}（{{ correctTarget.归一规格 }}）；
          更正后规则版本升级，在途同步将触发撤回，已确认历史不受影响。
        </p>
        <label class="create-field">
          <span>新归一规格</span>
          <input v-model="correctSpec" data-testid="correct-spec" required placeholder="如 650g" />
        </label>
        <label class="create-field">
          <span>新源规格文本</span>
          <input v-model="correctSource" data-testid="correct-source" placeholder="如 650g/袋" />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="correctTarget = null">取消</button>
          <button class="btn primary" data-testid="correct-submit" type="submit">确认更正</button>
        </div>
      </form>
    </div>

    <div v-if="withdrawTarget" class="modal-backdrop" data-testid="withdraw-modal">
      <form class="modal" @submit.prevent="submitWithdraw">
        <h3>申请同步撤回 {{ withdrawTarget.同步批次 }}</h3>
        <p class="panel-desc">
          撤回申请提交后，接收方（规格匹配器）将同时处理原匹配单 {{ withdrawTarget.匹配批次 }}。
        </p>
        <label class="create-field">
          <span>撤回原因</span>
          <input v-model="withdrawReason" data-testid="withdraw-reason" placeholder="如 规则更正为 v2" />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="withdrawTarget = null">取消</button>
          <button class="btn primary" data-testid="withdraw-submit" type="submit">确认撤回</button>
        </div>
      </form>
    </div>

    <p v-if="message" class="panel-message" data-testid="sync-message">{{ message }}</p>
    <p v-if="error" class="error-text" data-testid="sync-error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import SpecReceiptTable from '@/views/SpecReceiptTable.vue'
import {
  SYNC_STATUSES,
  continueSync,
  correctRule,
  fetchEnabledRules,
  fetchReceipts,
  fetchSyncBatches,
  fmtTime,
  submitSync,
  withdrawSync,
  type EnabledRule,
  type SyncBatch,
  type SyncReceipt,
} from '@/api/spec-sync'

const emit = defineEmits<{ changed: [] }>()

const enabledRules = ref<EnabledRule[]>([])
const batches = ref<SyncBatch[]>([])
const receipts = ref<SyncReceipt[]>([])
const batchKeyword = ref('')
const batchStatus = ref('')
const submitRuleId = ref(0)
const submitGoods = ref('')
const submitting = ref(false)
const correctTarget = ref<EnabledRule | null>(null)
const correctSpec = ref('')
const correctSource = ref('')
const withdrawTarget = ref<SyncBatch | null>(null)
const withdrawReason = ref('')
const message = ref('')
const error = ref('')

const TERMINAL = ['已撤回', '不可继续']
const canContinue = (batch: SyncBatch) => !TERMINAL.includes(batch.同步状态)
const canWithdraw = (batch: SyncBatch) => ['待匹配', '匹配中'].includes(batch.同步状态)

function report(result: { ok: boolean; message?: string }) {
  if (result.ok) {
    message.value = result.message ?? '操作完成'
    error.value = ''
  } else {
    error.value = result.message ?? '操作失败'
    message.value = ''
  }
}

async function loadRules() {
  const payload = await fetchEnabledRules()
  enabledRules.value = payload.rules
  if (!submitRuleId.value && payload.rules.length) {
    submitRuleId.value = payload.rules[0].id
  }
}

async function loadBatches() {
  const payload = await fetchSyncBatches(batchKeyword.value.trim(), batchStatus.value)
  batches.value = payload.items
}

async function loadReceipts(keyword = '') {
  const payload = await fetchReceipts(keyword)
  receipts.value = payload.items
}

async function reloadAll() {
  await Promise.all([loadRules(), loadBatches(), loadReceipts()])
}

async function submitNewSync() {
  if (!submitRuleId.value) {
    error.value = '请先选择归一规则'
    return
  }
  submitting.value = true
  try {
    const result = await submitSync(submitRuleId.value, submitGoods.value.trim())
    report(result)
    if (result.ok) {
      submitGoods.value = ''
      await reloadAll()
      emit('changed')
    }
  } finally {
    submitting.value = false
  }
}

async function doContinue(batch: SyncBatch) {
  const result = await continueSync(batch.id)
  report(result)
  await reloadAll()
  emit('changed')
}

function openWithdraw(batch: SyncBatch) {
  withdrawReason.value = ''
  withdrawTarget.value = batch
}

async function submitWithdraw() {
  if (!withdrawTarget.value) return
  const result = await withdrawSync(withdrawTarget.value.id, withdrawReason.value.trim())
  report(result)
  if (result.ok) {
    withdrawTarget.value = null
    await reloadAll()
    emit('changed')
  }
}

function openCorrect(rule: EnabledRule) {
  correctSpec.value = ''
  correctSource.value = ''
  correctTarget.value = rule
}

async function submitCorrect() {
  if (!correctTarget.value) return
  const result = await correctRule(correctTarget.value.id, correctSpec.value.trim(), correctSource.value.trim())
  report(result)
  if (result.ok) {
    correctTarget.value = null
    await reloadAll()
    emit('changed')
  }
}

async function viewReceipt(batch: SyncBatch) {
  await loadReceipts(batch.同步批次)
  message.value = `已筛出 ${batch.同步批次} 的交接回执`
  error.value = ''
}

onMounted(async () => {
  try {
    await reloadAll()
  } catch {
    error.value = '规格同步数据读取失败'
  }
})
</script>
