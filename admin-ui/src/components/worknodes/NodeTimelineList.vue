<template>
  <div class="space-y-2">
    <div v-if="!nodes.length" class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
      当前范围还没有工作节点。请先由育成师派任务，或选择其他工种/员工。
    </div>
    <button
      v-for="node in nodes"
      :key="node.node_id"
      type="button"
      class="flex w-full items-start gap-3 rounded-xl border px-4 py-4 text-left transition"
      :class="node.node_id === selectedNodeId ? 'border-teal-300 bg-teal-50/70 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300'"
      @click="$emit('select', node.node_id)"
    >
      <div class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" :class="dotClass(node.status)" />
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <div class="font-medium text-slate-900">{{ node.title }}</div>
          <span class="rounded-full px-2 py-0.5 text-[10px] font-medium" :class="workNodeStatusClass(node.status)">
            {{ node.status_label }}
          </span>
        </div>
        <div class="mt-1 text-xs text-slate-500">
          {{ node.member_name }} · {{ node.work_type_title }}
          <span v-if="node.updated_at"> · {{ formatDate(node.updated_at) }}</span>
        </div>
        <div v-if="currentPhaseSummary(node)" class="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">
          {{ currentPhaseSummary(node) }}
        </div>
      </div>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { WorkNode, WorkNodeStatus } from '../../utils/workNodes'
import { workNodeStatusClass } from '../../utils/workNodes'

defineProps<{
  nodes: WorkNode[]
  selectedNodeId?: string
}>()

defineEmits<{
  select: [nodeId: string]
}>()

const formatDate = (value?: string | null) => {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const dotClass = (status: WorkNodeStatus) => {
  if (status === 'archived') return 'bg-slate-400'
  if (status === 'approved') return 'bg-emerald-500'
  if (status === 'submitted') return 'bg-violet-500'
  return 'bg-cyan-500'
}

const currentPhaseSummary = (node: WorkNode) => {
  const current = node.phases.find((item) => item.status === 'current')
    || [...node.phases].reverse().find((item) => item.status === 'done')
  return current?.summary || current?.label || ''
}
</script>
