<template>
  <table class="data-table" data-testid="receipt-table">
    <thead>
      <tr>
        <th>回执编号</th>
        <th>同步批次</th>
        <th>规则版本</th>
        <th>商品标识</th>
        <th>归一规格</th>
        <th>匹配方处理批次</th>
        <th>匹配方处理结果</th>
        <th>旧成果可用性</th>
        <th>撤回待办</th>
        <th>更新时间</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="receipt in items" :key="receipt.id" :data-testid="`receipt-${receipt.id}`">
        <td>{{ receipt.回执编号 }}</td>
        <td>{{ receipt.同步批次 }}</td>
        <td>{{ receipt.规则版本 }}</td>
        <td>{{ receipt.商品标识 }}</td>
        <td>{{ receipt.归一规格 }}</td>
        <td>{{ receipt.匹配方处理批次 || '—' }}</td>
        <td>{{ receipt.匹配方处理结果 }}</td>
        <td>{{ receipt.旧成果可用性 }}</td>
        <td>{{ receipt.撤回待办 }}</td>
        <td>{{ fmtTime(receipt.更新时间) }}</td>
        <td>{{ receipt.status }}</td>
      </tr>
      <tr v-if="!items.length">
        <td colspan="11" class="empty-state">暂无规格交接回执</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
import { fmtTime, type SyncReceipt } from '@/api/spec-sync'

defineProps<{ items: SyncReceipt[] }>()
</script>
