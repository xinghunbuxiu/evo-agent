<template>
  <div class="grid gap-4 md:grid-cols-3">
    <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 class="font-semibold text-slate-900">同步本地技能</h3>
      <p class="mt-2 text-sm text-slate-500">把当前租户 `skills/draft` 下的技能推送到 Git knowledge 仓库。</p>
      <button @click="syncSkills" class="mt-4 rounded-lg bg-teal-500 px-4 py-2 text-white transition-colors hover:bg-teal-600" :disabled="syncing">
        {{ syncing ? '同步中...' : '同步本地技能到 Git' }}
      </button>
      <p v-if="syncResult" class="mt-3 text-sm" :class="syncSuccess ? 'text-green-600' : 'text-rose-600'">{{ syncResult }}</p>
    </div>
    <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 class="font-semibold text-slate-900">导出租户经验</h3>
      <p class="mt-2 text-sm text-slate-500">把成长事件、重放校验记录和子女岗位经验卡片一起导出到 experiences 仓库，形成真正可沉淀的经验层。</p>
      <button @click="exportExperiencesToGit" class="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-white hover:bg-slate-800" :disabled="exportingExperiences">
        {{ exportingExperiences ? '导出中...' : '导出经验摘要' }}
      </button>
      <p v-if="experienceResult" class="mt-3 text-sm" :class="experienceSuccess ? 'text-green-600' : 'text-rose-600'">{{ experienceResult }}</p>
    </div>
    <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 class="font-semibold text-slate-900">导出成长报告</h3>
      <p class="mt-2 text-sm text-slate-500">把当前自主进化总览快照导出到 reports 仓库，便于后续回看和企业定制沉淀。</p>
      <button @click="exportReportToGit" class="mt-4 rounded-lg border border-slate-300 px-4 py-2 text-slate-700 hover:bg-slate-50" :disabled="exportingReport">
        {{ exportingReport ? '导出中...' : '导出成长总览' }}
      </button>
      <p v-if="reportResult" class="mt-3 text-sm" :class="reportSuccess ? 'text-green-600' : 'text-rose-600'">{{ reportResult }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { exportTenantExperiences, exportTenantReport, syncLocalSkills } from '../api/knowledge'

const props = defineProps<{ tenantId: string; refresh: () => Promise<void> }>()
const syncing = ref(false)
const exportingExperiences = ref(false)
const exportingReport = ref(false)
const syncResult = ref('')
const syncSuccess = ref(false)
const experienceResult = ref('')
const experienceSuccess = ref(false)
const reportResult = ref('')
const reportSuccess = ref(false)

const syncSkills = async () => {
  syncing.value = true
  syncResult.value = ''
  try {
    const res = await syncLocalSkills(props.tenantId)
    syncResult.value = res.success
      ? `${res.message}，成功同步 ${res.data?.count || 0} 个技能`
      : res.message || '同步失败'
    syncSuccess.value = res.success
    await props.refresh()
  } catch {
    syncResult.value = '❌ 同步失败'
    syncSuccess.value = false
  } finally {
    syncing.value = false
  }
}

const exportExperiencesToGit = async () => {
  exportingExperiences.value = true
  experienceResult.value = ''
  try {
    const res = await exportTenantExperiences(props.tenantId)
    experienceResult.value = res.success
      ? `${res.message}：${res.data?.file_path || ''} / 子女 ${res.data?.journal_summary?.member_count || 0} / 卡片 ${res.data?.journal_summary?.card_total || 0}`
      : res.message || '经验导出失败'
    experienceSuccess.value = res.success
  } catch {
    experienceResult.value = '经验导出失败'
    experienceSuccess.value = false
  } finally {
    exportingExperiences.value = false
  }
}

const exportReportToGit = async () => {
  exportingReport.value = true
  reportResult.value = ''
  try {
    const res = await exportTenantReport(props.tenantId)
    reportResult.value = res.success
      ? `${res.message}：${res.data?.file_path || ''}`
      : res.message || '成长总览导出失败'
    reportSuccess.value = res.success
  } catch {
    reportResult.value = '成长总览导出失败'
    reportSuccess.value = false
  } finally {
    exportingReport.value = false
  }
}
</script>
