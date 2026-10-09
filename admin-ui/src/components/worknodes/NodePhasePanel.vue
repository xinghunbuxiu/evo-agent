<template>
  <div class="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
    <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="text-sm font-semibold text-slate-900">节点流程</div>
        <div class="mt-1 text-xs text-slate-500">从思考到 Gitee 归档的 7 个阶段</div>
      </div>
      <div class="flex flex-wrap gap-2">
        <router-link
          :to="node.member_link"
          class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
        >
          员工工作台
        </router-link>
        <router-link
          :to="node.trainer_link"
          class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs text-white hover:bg-slate-800"
        >
          育成师处理
        </router-link>
      </div>
    </div>

    <div class="mb-4 rounded-lg border border-slate-200 bg-white px-3 py-3">
      <div class="text-sm font-medium text-slate-900">{{ node.title }}</div>
      <div class="mt-1 text-xs text-slate-500">{{ node.member_name }} · {{ node.work_type_title }}</div>
    </div>

    <ol class="space-y-3">
      <li
        v-for="phase in node.phases"
        :key="phase.key"
        class="rounded-lg border px-3 py-3"
        :class="phaseCardClass(phase.status)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="text-sm font-medium text-slate-900">{{ phase.label }}</div>
          <span class="rounded-full px-2 py-0.5 text-[10px] font-medium" :class="phaseBadgeClass(phase.status)">
            {{ phaseStatusLabel(phase.status) }}
          </span>
        </div>
        <div v-if="phase.summary" class="mt-2 text-sm leading-6 text-slate-700">{{ phase.summary }}</div>
        <div v-if="phase.detail" class="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-500">{{ phase.detail }}</div>
        <div v-if="phase.at" class="mt-2 text-[11px] text-slate-400">{{ formatDate(phase.at) }}</div>
      </li>
    </ol>

    <div class="mt-4 rounded-lg border border-slate-200 bg-white px-3 py-3">
      <div class="text-xs font-medium uppercase tracking-[0.12em] text-slate-400">Gitee 归档</div>
      <p class="mt-2 text-xs leading-5 text-slate-600">{{ archiveHint }}</p>
      <ul v-if="archiveFiles.length" class="mt-2 space-y-1 text-[10px] text-slate-500">
        <li v-for="file in archiveFiles.slice(0, 6)" :key="file">{{ file }}</li>
      </ul>
      <div v-if="node.archive?.target_url" class="mt-2">
        <a
          :href="node.archive.target_url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-xs text-teal-700 hover:underline"
        >
          打开 experiences 仓库
        </a>
      </div>
      <button
        v-if="node.archive?.status === 'local_only'"
        type="button"
        class="mt-3 ml-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
        :disabled="archiving"
        @click="runRetryArchive"
      >
        {{ archiving ? '同步中...' : '重试同步本地归档' }}
      </button>
      <button
        v-if="canArchive"
        type="button"
        class="mt-3 rounded-lg border border-teal-300 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-800 hover:bg-teal-100 disabled:opacity-60"
        :disabled="archiving"
        @click="runArchive"
      >
        {{ archiving ? '归档中...' : (node.status === 'archived' ? '重新归档' : '立即归档') }}
      </button>
      <p v-if="archiveMessage" class="mt-2 text-xs" :class="archiveSuccess ? 'text-green-600' : 'text-red-600'">
        {{ archiveMessage }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { archiveWorkNode, retryWorkNodeArchive } from '../../api/workNodes'
import { companyConsoleKey } from '../../composables/companyConsole'
import type { WorkNode, WorkNodePhaseStatus } from '../../utils/workNodes'

const props = defineProps<{
  node: WorkNode
}>()

const consoleCtx = inject(companyConsoleKey)
const archiving = ref(false)
const archiveMessage = ref('')
const archiveSuccess = ref(false)

const archiveHint = computed(() => {
  const meta = props.node.archive
  if (meta?.gitee_path) return `已写入 Gitee：${meta.gitee_path}`
  if (meta?.local_root) return `已落盘本地：${meta.local_root}`
  return props.node.archive_hint || '任务确认后可归档到 experiences 仓库'
})

const archiveFiles = computed(() => props.node.archive?.files || [])

const canArchive = computed(() => (
  props.node.status === 'approved' || props.node.status === 'archived'
))

const runRetryArchive = async () => {
  archiving.value = true
  archiveMessage.value = ''
  try {
    const result = await retryWorkNodeArchive(props.node.task_id, {
      tenant_id: consoleCtx?.tenantId.value || 'default',
    })
    archiveSuccess.value = result.archive?.status === 'archived'
    archiveMessage.value = result.message || result.archive?.next_action || '同步完成'
    await consoleCtx?.refreshOverview()
  } catch (error) {
    archiveSuccess.value = false
    archiveMessage.value = error instanceof Error ? error.message : '同步失败'
  } finally {
    archiving.value = false
  }
}

const runArchive = async () => {
  archiving.value = true
  archiveMessage.value = ''
  try {
    const result = await archiveWorkNode(props.node.task_id, {
      tenant_id: consoleCtx?.tenantId.value || 'default',
    })
    archiveSuccess.value = true
    archiveMessage.value = result.message || '归档完成'
    await consoleCtx?.refreshOverview()
  } catch (error) {
    archiveSuccess.value = false
    archiveMessage.value = error instanceof Error ? error.message : '归档失败'
  } finally {
    archiving.value = false
  }
}

const formatDate = (value?: string | null) => {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const phaseStatusLabel = (status: WorkNodePhaseStatus) => {
  if (status === 'done') return '已完成'
  if (status === 'current') return '当前'
  if (status === 'skipped') return '跳过'
  return '待进入'
}

const phaseBadgeClass = (status: WorkNodePhaseStatus) => {
  if (status === 'done') return 'bg-emerald-100 text-emerald-800'
  if (status === 'current') return 'bg-cyan-100 text-cyan-800'
  if (status === 'skipped') return 'bg-slate-100 text-slate-500'
  return 'bg-amber-100 text-amber-800'
}

const phaseCardClass = (status: WorkNodePhaseStatus) => {
  if (status === 'current') return 'border-cyan-200 bg-cyan-50/50'
  if (status === 'done') return 'border-slate-200 bg-white'
  if (status === 'skipped') return 'border-transparent bg-transparent opacity-60'
  return 'border-dashed border-slate-200 bg-white/60'
}
</script>
