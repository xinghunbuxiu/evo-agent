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

    <section
      v-else-if="missionRun && activeSection === 'recovery'"
      class="space-y-4"
    >
      <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        复核只读取原始 Broker/Validator 状态并重新验签。恢复操作不会重新运行 Skill；若原始执行或独立验收证据不完整，服务端会拒绝发布。
      </div>
      <div
        v-for="item in recoveryItems"
        :key="item.task_id"
        class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-900">{{ item.title || item.skill_id }}</div>
            <div class="mt-1 break-all font-mono text-xs text-slate-500">
              {{ item.skill_id }} · {{ item.node_id }} · {{ item.task_id }}
            </div>
            <div class="mt-2 text-xs text-slate-500">
              中断原因：{{ item.recovery_reason || '未知' }} · {{ formatTime(item.interrupted_at) }}
            </div>
          </div>
          <span class="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800">
            {{ item.recovery_assessment.status }}
          </span>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div class="rounded-lg bg-slate-50 p-3">
            <div class="text-xs text-slate-500">Broker Stage</div>
            <div class="mt-1 text-sm font-medium text-slate-800">{{ item.verified_receipts.broker_stage || 'not_checked' }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 p-3">
            <div class="text-xs text-slate-500">Broker Execution</div>
            <div class="mt-1 text-sm font-medium text-slate-800">{{ item.verified_receipts.broker_execution || 'not_checked' }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 p-3">
            <div class="text-xs text-slate-500">Independent Validator</div>
            <div class="mt-1 text-sm font-medium text-slate-800">{{ item.verified_receipts.validator || item.validator_status.status || 'not_checked' }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 p-3">
            <div class="text-xs text-slate-500">Artifact Promotion</div>
            <div class="mt-1 text-sm font-medium text-slate-800">{{ item.verified_receipts.broker_promotion || item.broker_status.promotion?.status || 'not_checked' }}</div>
          </div>
        </div>
        <div class="mt-3 text-xs text-slate-600">
          {{ item.recovery_assessment.next_step }}
        </div>
        <div class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
          <div class="break-all text-xs text-slate-500">
            {{ item.skill_binding?.skill_version || '未固定版本' }}
            <span v-if="item.skill_binding?.content_sha256"> · SHA256 {{ item.skill_binding.content_sha256 }}</span>
          </div>
          <button
            v-if="canResumeReplayPromotion(item)"
            type="button"
            :disabled="recoveryBusyKey === item.task_id"
            class="rounded-lg bg-teal-700 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
            @click="resumeReplayPromotion(item)"
          >
            {{ recoveryBusyKey === item.task_id ? '正在复核并恢复...' : '管理员确认恢复发布' }}
          </button>
        </div>
      </div>
      <div v-if="!recoveryItems.length" class="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        当前 Mission 没有待复核的 Skill Replay。
      </div>
    </section>

    <MissionRunDetailPanel
      v-else-if="missionRun"
      :run="missionRun"
      :section="activeSection"
      :continue-disabled="continuing"
       :show-continue-button="true"
      :replay-busy-key="replayBusyKey"
      :staffing-options="staffingOptions"
      :staffing-busy-key="staffingBusyKey"
      @continue="continueCurrentMission"
      @replay-skill="replayCurrentSkill"
      @approve-staffing="approveCurrentStaffing"
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
import {
  approveMissionStaffing,
  continueMission,
  getMissionRun,
  getMissionStaffingOptions,
  listMissionSkillReplayRecoveryReviews,
  resumeMissionSkillReplayPromotion,
  replayMissionSkill,
  type MissionRun,
  type MissionStaffingOptions,
  type MissionSkillReplayRecoveryItem,
} from '../api/missions'

type MissionDetailSection = 'overview' | 'actions' | 'growth' | 'plan' | 'recovery'

const route = useRoute()
const router = useRouter()
const activeSection = ref<MissionDetailSection>('overview')
const missionRun = ref<MissionRun | null>(null)
const loading = ref(false)
const continuing = ref(false)
const replayBusyKey = ref('')
const staffingOptions = ref<MissionStaffingOptions | null>(null)
const staffingBusyKey = ref('')
const recoveryItems = ref<MissionSkillReplayRecoveryItem[]>([])
const recoveryBusyKey = ref('')
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
    recovery: {
      title: `${title} · Skill Replay 复核`,
      description: '核验 Broker 与 Validator 的原始签名回执；仅允许管理员按原请求恢复发布，不会重新执行 Skill。',
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
  { key: 'recovery', title: 'Replay 复核', badge: recoveryItems.value.length ? String(recoveryItems.value.length) : undefined, active: activeSection.value === 'recovery' },
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
  if (section === 'actions' || section === 'growth' || section === 'plan' || section === 'recovery') return section
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
    staffingOptions.value = null
    recoveryItems.value = []
    if (missionRun.value?.tenant_id) {
      try {
        const reviews = await listMissionSkillReplayRecoveryReviews(missionRun.value.tenant_id, 200)
        recoveryItems.value = (reviews.data?.items || []).filter(
          (item) => item.mission_run_id === missionRun.value?.mission_run_id,
        )
      } catch (recoveryError) {
        // Recovery review is an admin-only optional view; it must not block normal Mission details.
        console.warn('Failed to load Skill Replay recovery reviews:', recoveryError)
      }
    }
    if (missionRun.value?.staffing_requests?.length) {
      try {
        const options = await getMissionStaffingOptions(id, missionRun.value.tenant_id)
        staffingOptions.value = options.data || null
      } catch (staffingError) {
        console.warn('Failed to load Mission staffing options:', staffingError)
      }
    }
  } catch (error) {
    console.error('Failed to load mission run:', error)
    missionRun.value = null
    staffingOptions.value = null
  } finally {
    loading.value = false
  }
}

const formatTime = (value?: string) => {
  if (!value) return '--'
  return value.slice(0, 19).replace('T', ' ')
}

const canResumeReplayPromotion = (item: MissionSkillReplayRecoveryItem) => (
  item.candidate_binding_status === 'pinned'
  && item.verified_receipts.broker_stage === 'verified'
  && item.verified_receipts.broker_execution === 'verified'
  && item.verified_receipts.execution_succeeded === true
  && item.verified_receipts.validator === 'verified'
  && item.verified_receipts.broker_promotion !== 'invalid'
  && Boolean(item.stage_request_id && item.execution_request_id && item.validation_request_id && item.promotion_request_id)
)

const resumeReplayPromotion = async (item: MissionSkillReplayRecoveryItem) => {
  if (!missionRun.value || recoveryBusyKey.value) return
  const confirmed = window.confirm(
    `确认复核原始签名证据，并按原请求恢复 ${item.skill_id} 的 Artifact 发布？此操作不会重新执行 Skill。`
  )
  if (!confirmed) return
  recoveryBusyKey.value = item.task_id
  message.value = ''
  try {
    const response = await resumeMissionSkillReplayPromotion(
      item.mission_run_id,
      item.skill_id,
      item.task_id,
    )
    success.value = Boolean(response.success)
    message.value = response.message || (response.success ? 'Skill Artifact 已恢复发布。' : '恢复未完成，请继续人工复核。')
    await loadMissionRun()
  } catch (error: unknown) {
    success.value = false
    message.value = error instanceof Error ? error.message : '恢复结果不确定，请刷新复核队列。'
    await loadMissionRun()
  } finally {
    recoveryBusyKey.value = ''
  }
}

const approveCurrentStaffing = async (payload: {
  nodeId: string
  employeeMemberId: string
  workerId: string
}) => {
  const current = missionRun.value
  const nodeId = String(payload.nodeId || '').trim()
  const employeeMemberId = String(payload.employeeMemberId || '').trim()
  const workerId = String(payload.workerId || '').trim()
  if (!current || !nodeId || !employeeMemberId || !workerId || staffingBusyKey.value) return
  const confirmed = window.confirm(
    `确认将 Mission 节点 ${nodeId} 派给员工 ${employeeMemberId} 的 Worker ${workerId}？批准后会立即恢复该节点派遣。`
  )
  if (!confirmed) return
  staffingBusyKey.value = nodeId
  message.value = ''
  try {
    const response = await approveMissionStaffing(current.mission_run_id, {
      tenant_id: current.tenant_id,
      node_id: nodeId,
      employee_member_id: employeeMemberId,
      worker_id: workerId,
    })
    if (!response.success) {
      success.value = false
      message.value = response.message || '人员审批未成功；请刷新并核对 Mission 状态。'
      await loadMissionRun()
      return
    }
    success.value = true
    message.value = '人员派遣已批准，Mission 已尝试恢复对应节点。'
    await loadMissionRun()
  } catch (error: unknown) {
    success.value = false
    message.value = error instanceof Error ? error.message : '人员派遣审批失败'
    await loadMissionRun()
  } finally {
    staffingBusyKey.value = ''
  }
}

const replayCurrentSkill = async (payload: { skillId: string; nodeId: string }) => {
  const current = missionRun.value
  const skillId = String(payload.skillId || '').trim()
  const nodeId = String(payload.nodeId || '').trim()
  if (!current || !skillId || !nodeId || replayBusyKey.value) return

  const confirmed = window.confirm(
    `将 ${skillId} 提交到隔离 Broker 执行。执行成功后还会请求独立 Validator；只有签名验收通过才可能发布不可变 Artifact。是否继续？`
  )
  if (!confirmed) return

  replayBusyKey.value = `${nodeId}:${skillId}`
  message.value = ''
  try {
    const response = await replayMissionSkill(
      current.mission_run_id,
      skillId,
      nodeId,
      crypto.randomUUID(),
    )
    if (!response.success) {
      success.value = false
      message.value = response.message || 'Broker 回放请求未成功；请核对 Mission 动作链状态。'
      await loadMissionRun()
      return
    }
    success.value = true
    message.value = 'Broker 隔离回放已完成；已刷新 Mission 动作链以读取签名证据、独立验证和发布状态。'
    await loadMissionRun()
  } catch (error: unknown) {
    success.value = false
    message.value = error instanceof Error
      ? error.message
      : 'Broker 回放结果不确定；请先刷新 Mission 动作链核对状态，不要直接重复执行。'
    await loadMissionRun()
  } finally {
    replayBusyKey.value = ''
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
