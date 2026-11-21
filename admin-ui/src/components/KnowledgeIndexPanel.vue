<template>
  <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <h2 class="text-lg font-semibold text-slate-900">知识索引状态</h2>
    <div class="mt-4 grid gap-3 sm:grid-cols-3">
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
        <div class="text-2xl font-bold text-slate-900">{{ summary?.repo_count ?? 0 }}</div>
        <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Repos</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
        <div class="text-2xl font-bold text-slate-900">{{ summary?.indexed_repo_count ?? 0 }}</div>
        <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Indexed</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
        <div class="text-2xl font-bold text-slate-900">{{ summary?.total_entries ?? 0 }}</div>
        <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Entries</div>
      </div>
    </div>
    <div class="mt-4 flex flex-wrap gap-3">
      <button class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60" :disabled="scanning" @click="scanKnowledgeIndex">
        {{ scanning ? '扫描中...' : '扫描知识索引' }}
      </button>
      <button class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60" :disabled="exporting" @click="exportIndexTemplate">
        {{ exporting ? '导出中...' : '导出索引模板' }}
      </button>
    </div>
    <p v-if="result" class="mt-3 text-sm" :class="success ? 'text-green-600' : 'text-rose-600'">{{ result }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { exportGitKnowledgeIndexTemplate, scanTenantGitKnowledge, type GitKnowledgeRepoIndexSummary } from '../api/git'

const props = defineProps<{
  tenantId: string
  summary: GitKnowledgeRepoIndexSummary | null
  refresh: () => Promise<void>
}>()
const emit = defineEmits<{
  'update:summary': [summary: GitKnowledgeRepoIndexSummary | null]
}>()

const scanning = ref(false)
const exporting = ref(false)
const result = ref('')
const success = ref(false)

const scanKnowledgeIndex = async () => {
  scanning.value = true
  result.value = ''
  try {
    const res = await scanTenantGitKnowledge(props.tenantId)
    emit('update:summary', res.data?.repo_index_summary || null)
    result.value = res.success
      ? `${res.message || '扫描完成'}，已索引 ${res.data?.repo_index_summary?.indexed_repo_count || 0} 个仓库`
      : res.message || '扫描失败'
    success.value = res.success
    await props.refresh()
  } catch (error) {
    console.error('Failed to scan knowledge index:', error)
    result.value = '知识索引扫描失败'
    success.value = false
  } finally {
    scanning.value = false
  }
}

const exportIndexTemplate = async () => {
  exporting.value = true
  result.value = ''
  try {
    const res = await exportGitKnowledgeIndexTemplate(props.tenantId, { scan_after_write: true })
    emit('update:summary', res.data?.repo_index_summary || null)
    result.value = res.success
      ? `${res.message || '导出完成'}：${res.data?.file_path || ''}`
      : res.message || '导出失败'
    success.value = res.success
  } catch (error) {
    console.error('Failed to export knowledge index template:', error)
    result.value = '索引模板导出失败'
    success.value = false
  } finally {
    exporting.value = false
  }
}
</script>
