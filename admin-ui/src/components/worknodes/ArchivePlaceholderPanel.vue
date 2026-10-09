<template>
  <div class="space-y-3">
    <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
      <div class="font-medium text-slate-900">Gitee 节点归档</div>
      <p class="mt-2 leading-6">
        育成确认后自动写入（或手动补归档）。路径：
        <code class="rounded bg-white px-1 py-0.5 text-xs">experiences/tenants/.../nodes/{task_id}/</code>
      </p>
    </div>

    <article
      v-for="node in archivableNodes"
      :key="node.node_id"
      class="rounded-xl border border-slate-200 bg-white px-4 py-4"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="font-medium text-slate-900">{{ node.title }}</div>
        <span class="rounded-full px-2 py-0.5 text-[10px]" :class="workNodeStatusClass(node.status)">
          {{ node.status_label }}
        </span>
      </div>
      <div class="mt-1 text-xs text-slate-500">{{ node.member_name }} · {{ node.work_type_title }}</div>
      <p class="mt-3 text-xs leading-5 text-slate-600">{{ archiveHint(node) }}</p>
      <div v-if="node.archive?.files?.length" class="mt-2 text-[10px] text-slate-500">
        已写入 {{ node.archive.files.length }} 个文件
      </div>
      <button
        v-if="node.archive?.status === 'local_only'"
        type="button"
        class="mt-3 ml-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
        :disabled="archivingId === node.task_id"
        @click="runRetryArchive(node)"
      >
        {{ archivingId === node.task_id ? '同步中...' : '重试同步本地归档' }}
      </button>
      <button
        v-if="canArchive(node)"
        type="button"
        class="mt-3 rounded-lg border border-teal-300 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-800 hover:bg-teal-100 disabled:opacity-60"
        :disabled="archivingId === node.task_id"
        @click="runArchive(node)"
      >
        {{ archivingId === node.task_id ? '归档中...' : (node.status === 'archived' ? '重新归档' : '立即归档到 Gitee') }}
      </button>
    </article>

    <div v-if="!archivableNodes.length" class="text-sm text-slate-500">
      还没有可归档节点（需任务状态为已确认）。
    </div>
    <p v-if="archiveMessage" class="text-sm" :class="archiveSuccess ? 'text-green-600' : 'text-red-600'">
      {{ archiveMessage }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { archiveWorkNode, retryWorkNodeArchive } from '../../api/workNodes'
import type { WorkNode } from '../../utils/workNodes'
import { workNodeStatusClass } from '../../utils/workNodes'
import { companyConsoleKey } from '../../composables/companyConsole'

const props = defineProps<{
  nodes: WorkNode[]
}>()

const consoleCtx = inject(companyConsoleKey)
const archivingId = ref('')
const archiveMessage = ref('')
const archiveSuccess = ref(false)

const archivableNodes = computed(() => (
  props.nodes.filter((item) => ['approved', 'archived'].includes(item.status))
))

const archiveHint = (node: WorkNode) => {
  const meta = node.archive
  if (meta?.status === 'archived') {
    return `已同步 Gitee：${meta.gitee_path || meta.target_repo || 'experiences'}${meta.integrity_verified === true ? ' · 回读校验通过' : ''}`
  }
  if (meta?.status === 'local_only') {
    return `仅本地保存，尚未确认远端同步：${meta.local_root || meta.gitee_path || '本地归档目录'}`
  }
  if (meta?.status === 'failed') return `归档失败：${meta.reason || meta.next_action || '请检查配置后重试'}`
  if (meta?.gitee_path) return `归档路径：${meta.gitee_path}`
  if (meta?.local_root) return `本地落盘：${meta.local_root}`
  return node.archive_hint || '任务确认后可归档'
}

const canArchive = (node: WorkNode) => node.status === 'approved' || node.status === 'archived'

const runRetryArchive = async (node: WorkNode) => {
  archivingId.value = node.task_id
  archiveMessage.value = ''
  try {
    const result = await retryWorkNodeArchive(node.task_id, {
      tenant_id: consoleCtx?.tenantId.value || 'default',
    })
    archiveSuccess.value = result.archive?.status === 'archived'
    archiveMessage.value = result.message || result.archive?.next_action || '同步完成'
    await consoleCtx?.refreshOverview()
  } catch (error) {
    archiveSuccess.value = false
    archiveMessage.value = error instanceof Error ? error.message : '同步失败'
  } finally {
    archivingId.value = ''
  }
}

const runArchive = async (node: WorkNode) => {
  archivingId.value = node.task_id
  archiveMessage.value = ''
  try {
    const result = await archiveWorkNode(node.task_id, {
      tenant_id: consoleCtx?.tenantId.value || 'default',
    })
    archiveSuccess.value = result.archive?.status === 'archived'
    archiveMessage.value = result.message || result.archive?.next_action || '归档完成'
    await consoleCtx?.refreshOverview()
  } catch (error) {
    archiveSuccess.value = false
    archiveMessage.value = error instanceof Error ? error.message : '归档失败'
  } finally {
    archivingId.value = ''
  }
}
</script>
