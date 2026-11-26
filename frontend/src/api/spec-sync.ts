/** 规格同步交接接口：归一器与匹配工作台之间的批次、撤回与交接回执。 */
import { request } from './client'

export type EnabledRule = {
  id: number
  规则名称: string
  规则版本: string
  源规格文本: string
  归一规格: string
  单位换算: string
  status: string
}

export type SyncBatch = {
  id: number
  同步批次: string
  规则ID: number
  规则名称: string
  规则版本: string
  商品标识: string
  归一规格: string
  源规格文本: string
  幂等键: string
  匹配记录ID: number | null
  匹配批次: string
  同步状态: string
  撤回原因: string
  创建时间: string
  更新时间: string
  确认时间: string
}

export type SyncReceipt = {
  id: number
  回执编号: string
  同步批次: string
  规则名称: string
  规则版本: string
  商品标识: string
  归一规格: string
  匹配方处理批次: string
  匹配方处理结果: string
  旧成果可用性: string
  撤回待办: string
  交接时间: string
  更新时间: string
  status: string
}

export type SyncCandidate = {
  同步批次ID: number
  同步批次: string
  商品标识: string
  候选规格: string
  规则版本: string
  同步状态: string
  撤回原因: string
  匹配记录ID: number | null
  匹配单状态: string
  资格: string
}

export type ConfirmedSync = {
  同步批次: string
  商品标识: string
  归一规格: string
  规则版本: string
  资格: string
  匹配单状态: string
  确认时间: string
}

export type SyncResult = {
  ok: boolean
  message?: string
  reused?: boolean
  batch?: SyncBatch
  receipt?: SyncReceipt
  规则版本?: string
  withdrawn?: string[]
}

export const SYNC_STATUSES = ['待匹配', '匹配中', '已确认', '撤回中', '已撤回', '不可继续']

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  return (await response.json()) as T
}

function post(body: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(body) }
}

/** 把时间戳截到分钟，方便运营核对。 */
export function fmtTime(value: string | undefined): string {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

export const fetchEnabledRules = () =>
  call<{ ok: boolean; rules: EnabledRule[] }>('/api/spec-sync/enabled-rules')

export const fetchSyncBatches = (keyword = '', status = '') =>
  call<{ ok: boolean; items: SyncBatch[]; total: number }>(
    `/api/spec-sync/batches?keyword=${encodeURIComponent(keyword)}&status=${encodeURIComponent(status)}`,
  )

export const submitSync = (ruleId: number, goods: string) =>
  call<SyncResult>('/api/spec-sync/batches', post({ rule_id: ruleId, goods }))

export const continueSync = (batchId: number) =>
  call<SyncResult>(`/api/spec-sync/batches/${batchId}/continue`, post({}))

export const withdrawSync = (batchId: number, reason: string) =>
  call<SyncResult>(`/api/spec-sync/batches/${batchId}/withdraw`, post({ reason }))

export const correctRule = (ruleId: number, 归一规格: string, 源规格文本: string) =>
  call<SyncResult>(`/api/spec-sync/rules/${ruleId}/correct`, post({ 归一规格, 源规格文本 }))

export const fetchReceipts = (keyword = '') =>
  call<{ ok: boolean; items: SyncReceipt[]; total: number }>(
    `/api/spec-sync/receipts?keyword=${encodeURIComponent(keyword)}`,
  )

export const fetchCandidates = () =>
  call<{ ok: boolean; items: SyncCandidate[]; total: number }>('/api/spec-sync/candidates')

export const startMatch = (batchId: number) =>
  call<SyncResult>(`/api/spec-sync/batches/${batchId}/start`, post({}))

export const confirmMatch = (batchId: number) =>
  call<SyncResult>(`/api/spec-sync/batches/${batchId}/confirm`, post({}))

export const resolveWithdrawal = (batchId: number, mode: 'finish_old' | 'redo_new') =>
  call<SyncResult>(`/api/spec-sync/batches/${batchId}/resolve`, post({ mode }))

export const fetchConfirmed = (keyword = '') =>
  call<{ ok: boolean; items: ConfirmedSync[]; total: number }>(
    `/api/spec-sync/confirmed?keyword=${encodeURIComponent(keyword)}`,
  )
