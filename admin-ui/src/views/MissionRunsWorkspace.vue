<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="Mission · 运行"
      title="Mission 运行列表"
      description="查看 autonomy mission 的动作链与续跑状态；单次详情可进入动作、成长轨迹与下一轮计划。"
      :loading="loading"
      refresh-label="刷新列表"
      :back-to="{ path: '/dashboard' }"
      back-label="返回公司总览"
      @refresh="loadRuns"
    >
      <template #actions>
        <router-link
          to="/organization/tasks"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          任务队列
        </router-link>
        <router-link
          to="/organization/evolution"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          成长控制台
        </router-link>
      </template>
    </WorkspacePageHeader>

    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table class="w-full">
        <thead class="border-b bg-slate-50">
          <tr class="text-left text-sm text-slate-500">
            <th class="px-4 py-3 font-medium">Mission ID</th>
            <th class="px-4 py-3 font-medium">标题</th>
            <th class="px-4 py-3 font-medium">类型</th>
            <th class="px-4 py-3 font-medium">状态</th>
            <th class="px-4 py-3 font-medium">成员</th>
            <th class="px-4 py-3 font-medium">创建时间</th>
            <th class="px-4 py-3 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="run in runs"
            :key="run.mission_run_id"
            class="border-b last:border-0 hover:bg-slate-50"
          >
            <td class="px-4 py-3 font-mono text-xs text-slate-700">{{ run.mission_run_id }}</td>
            <td class="px-4 py-3 text-sm text-slate-900">{{ run.title || run.mission_kind }}</td>
            <td class="px-4 py-3 text-sm text-slate-600">{{ run.mission_kind }}</td>
            <td class="px-4 py-3">
              <StatusBadge :status="run.status" />
            </td>
            <td class="px-4 py-3 text-sm text-slate-600">
              {{ memberLabel(run) }}
            </td>
            <td class="px-4 py-3 text-sm text-slate-500">{{ formatTime(run.created_at) }}</td>
            <td class="px-4 py-3">
              <router-link
                :to="detailRoute(run.mission_run_id)"
                class="text-sm font-medium text-teal-700 hover:text-teal-900"
              >
                查看详情
              </router-link>
            </td>
          </tr>
          <tr v-if="!runs.length">
            <td colspan="7" class="px-4 py-10 text-center text-sm text-slate-500">
              {{ loading ? '加载中...' : '暂无 mission 运行记录' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import { listMissionRuns, type MissionRun } from '../api/missions'

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const runs = ref<MissionRun[]>([])
const loading = ref(false)

const formatTime = (value?: string) => {
  if (!value) return '--'
  return value.slice(0, 19).replace('T', ' ')
}

const memberLabel = (run: MissionRun) => {
  const name = String(run.context?.member_name || '').trim()
  const memberId = String(run.context?.member_id || run.member_reflection_member_id || '').trim()
  return name || memberId || '--'
}

const detailRoute = (missionRunId: string) => ({
  path: `/organization/missions/${encodeURIComponent(missionRunId)}`,
})

const loadRuns = async () => {
  loading.value = true
  try {
    const result = await listMissionRuns(tenantId.value || 'default', 50)
    runs.value = result.data?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(loadRuns)
</script>
