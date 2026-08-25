<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="Mission · 运行"
      :title="sectionMeta.title"
      :description="sectionMeta.description"
      :loading="loading"
      refresh-label="刷新"
      :back-to="listRoute"
      back-label="返回 Mission 列表"
      @refresh="loadMissionRun"
    >
      <template #actions>
        <span
          v-if="missionRun?.status"
          class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
        >
          {{ missionRun.status }}
        </span>
        <router-link
          v-if="memberWorkspaceRoute"
          :to="memberWorkspaceRoute"
          class="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-50"
        >
          员工工作台
        </router-link>
      </template>
    </WorkspacePageHeader>

    <WorkspaceSubNav
      v-if="missionRun"
      orientation="horizontal"
      :items="subNavItems"
      @select="onSectionSelect"
    />

    <div v-if="message" class="rounded-xl px-4 py-3 text-sm" :class="success ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'">
      {{ message }}
    </div>

    <div v-if="loading && !missionRun" class="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
      正在加载 mission 详情...
    </div>

    <MissionRunDetailPanel
      v-else-if="missionRun"
      :run="missionRun"
      :section="activeSection"
      :continue-disabled="continuing"
      :show-continue-button="true"
      @continue="continueCurrentMission"
    />

    <div v-else class="rounded-2xl border border-rose-200 bg-white p-8 text-center text-sm text-rose-600">
      没有找到对应的 mission run，可能已经被清理或 mission_run_id 不存在。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MissionRunDetailPanel from '../components/MissionRunDetailPanel.vue'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav, { type WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import { continueMission, getMissionRun, type MissionRun } from '../api/missions'

type MissionDetailSection = 'overview' | 'actions' | 'growth' | 'plan'

const route = useRoute()
const router = useRouter()
const activeSection = ref<MissionDetailSection>('overview')
const missionRun = ref<MissionRun | null>(null)
const loading = ref(false)
const continuing = ref(false)
const message = ref('')
const success = ref(false)
let refreshTimer: number | null = null

const listRoute = { path: '/organization/missions' }

const missionRunId = () => String(route.params.missionRunId || '').trim()

const sectionMeta = computed(() => {
  const title = missionRun.value?.title || missionRun.value?.mission_kind || 'Mission 运行详情'
  const map: Record<MissionDetailSection, { title: string; description: string }> = {
    overview: {
      title,
      description: 'Mission 目标、绑定成员、会话进度与 worker 摘要。',
    },
    actions: {
      title: `${title} · 动作链`,
      description: '各节点任务状态、学习关联与执行结果。',
    },
    growth: {
      title: `${title} · 成长轨迹`,
      description: '本次 mission 沉淀的经验与时间线事件。',
    },
    plan: {
      title: `${title} · 续跑计划`,
      description: '下一轮 focus 与 next steps；可在此继续 mission。',
    },
  }
  return map[activeSection.value]
})

const actionCount = computed(() => missionRun.value?.actions.length ?? 0)
const growthCount = computed(() => missionRun.value?.summary?.growth_timeline?.length ?? 0)
const planStepCount = computed(() => (
  (missionRun.value?.summary?.next_cycle_plan?.next_steps?.length ?? 0)
  + (missionRun.value?.summary?.next_cycle_plan?.focus_points?.length ?? 0)
))

const subNavItems = computed<WorkspaceSubNavItem[]>(() => ([
  { key: 'overview', title: '摘要', active: activeSection.value === 'overview' },
  { key: 'actions', title: '动作链', badge: String(actionCount.value), active: activeSection.value === 'actions' },
  { key: 'growth', title: '成长', badge: String(growthCount.value), active: activeSection.value === 'growth' },
  { key: 'plan', title: '续跑', badge: planStepCount.value ? String(planStepCount.value) : undefined, active: activeSection.value === 'plan' },
]))

const memberWorkspaceRoute = computed(() => {
  const memberId = String(
    missionRun.value?.context?.member_id
    || missionRun.value?.member_reflection_member_id
    || '',
  ).trim()
  if (!memberId) return null
  return { path: `/organization/child/${encodeURIComponent(memberId)}/workspace` }
})

const normalizeSection = (value: unknown): MissionDetailSection => {
  const section = String(value || '').trim()
  if (section === 'actions' || section === 'growth' || section === 'plan') return section
  return 'overview'
}

const onSectionSelect = (key: string) => {
  const section = normalizeSection(key)
  activeSection.value = section
  router.replace({
    path: route.path,
    query: section === 'overview' ? {} : { section },
  })
}

const loadMissionRun = async () => {
  const id = missionRunId()
  if (!id) {
    missionRun.value = null
    return
  }
  loading.value = true
  try {
    const result = await getMissionRun(id)
    missionRun.value = result.data || null
  } catch (error) {
    console.error('Failed to load mission run:', error)
    missionRun.value = null
  } finally {
    loading.value = false
  }
}

const continueCurrentMission = async () => {
  const current = missionRun.value
  if (!current) return
  continuing.value = true
  message.value = ''
  try {
    const result = await continueMission(current.mission_run_id)
    const continued = result.data?.continued_mission_run
    success.value = true
    message.value = continued
      ? `已启动下一轮 mission：${continued.mission_run_id}`
      : '已启动下一轮 mission'
    if (continued?.mission_run_id) {
      await router.replace({
        path: `/organization/missions/${encodeURIComponent(continued.mission_run_id)}`,
        query: route.query.section ? { section: route.query.section } : {},
      })
    } else {
      await loadMissionRun()
    }
  } catch (error: unknown) {
    success.value = false
    message.value = error instanceof Error ? error.message : '继续 mission 失败'
  } finally {
    continuing.value = false
  }
}

watch(() => route.params.missionRunId, () => {
  message.value = ''
  loadMissionRun().catch((error) => {
    console.error('Failed to reload mission detail:', error)
  })
})

watch(() => route.query.section, (value) => {
  activeSection.value = normalizeSection(value)
}, { immediate: true })

onMounted(async () => {
  await loadMissionRun()
  refreshTimer = window.setInterval(() => {
    loadMissionRun().catch((error) => {
      console.error('Failed to refresh mission detail:', error)
    })
  }, 8000)
})

onUnmounted(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>
