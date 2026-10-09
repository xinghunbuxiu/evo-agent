<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
      <header class="rounded-2xl border border-slate-200 bg-white px-5 py-5 shadow-sm">
      <div class="text-xs font-medium text-slate-500">公司总览</div>
      <h1 class="mt-2 text-2xl font-semibold text-slate-900">经营看板</h1>
      <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
        查看接单进度、岗位交付与收支结论；从左侧组织树进入工种、员工与接单台。
      </p>
      <div class="mt-4 flex flex-wrap gap-2 text-xs">
        <router-link to="/organization/intake?section=create" class="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-white hover:bg-slate-800">
          新建接单
        </router-link>
        <router-link to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary" class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-teal-800 hover:bg-teal-100">
          育成与派工
        </router-link>
        <router-link to="/organization/parent/workspace?section=worktypes" class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700 hover:bg-slate-100">
          工种配置
        </router-link>
      </div>
    </header>

    <div v-if="loading" class="rounded-2xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
      正在同步节点与财务数据…
    </div>

    <p v-else-if="loadError" class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {{ loadError }}
      <button type="button" class="ml-3 underline" @click="retryLoad">重试</button>
    </p>

    <template v-else>
      <MetricStrip :items="summaryMetrics" />

      <section class="grid gap-3 lg:grid-cols-2">
        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-slate-900">接单漏斗</h2>
              <p class="mt-1 text-xs text-slate-500">接入 → 分析分派 → 交付 → 结算</p>
            </div>
            <router-link
              to="/organization/intake"
              class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
            >
              接单台 →
            </router-link>
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div
              v-for="card in intakeFunnelCards"
              :key="card.key"
              class="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3"
            >
              <div class="text-[11px] uppercase tracking-[0.12em] text-slate-400">{{ card.label }}</div>
              <div class="mt-1 text-xl font-semibold text-slate-900">{{ card.value }}</div>
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-teal-200 bg-teal-50/40 p-4 shadow-sm">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-teal-950">岗位与成长</h2>
              <p class="mt-1 text-xs text-teal-800">建档带教 → 实战复盘 → 经验沉淀</p>
            </div>
            <router-link
              to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary"
              class="rounded-lg border border-teal-200 bg-white px-3 py-1.5 text-xs text-teal-800 hover:bg-teal-50"
            >
              育成师 →
            </router-link>
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div
              v-for="card in supplyGrowthCards"
              :key="card.key"
              class="rounded-xl border border-teal-100 bg-white px-3 py-3"
            >
              <div class="text-[11px] uppercase tracking-[0.12em] text-teal-600/80">{{ card.label }}</div>
              <div class="mt-1 text-xl font-semibold text-teal-950">{{ card.value }}</div>
            </div>
          </div>
          <router-link
            to="/organization/evolution"
            class="mt-3 inline-block text-xs font-medium text-teal-800 underline"
          >
            打开成长复盘
          </router-link>
        </div>
      </section>

      <section
        v-if="unboundMembers.length"
        class="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-4 shadow-sm"
      >
        <h2 class="text-sm font-semibold text-amber-950">待绑岗员工（{{ unboundMembers.length }}）</h2>
        <p class="mt-1 text-xs text-amber-800">没有对应工种，不会出现在业务部门树。请到育成师画像重新绑岗。</p>
        <ul class="mt-3 space-y-2 text-sm text-amber-900">
          <li
            v-for="member in unboundMembers"
            :key="String(member.member_id)"
            class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-white px-3 py-2"
          >
            <span>{{ member.name || member.member_id }}</span>
            <router-link
              to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary"
              class="text-xs font-medium text-amber-800 underline"
            >
              去育成师绑岗 →
            </router-link>
          </li>
        </ul>
      </section>

      <section
        v-if="commercialReadiness && commercialReadiness.score < 100"
        class="rounded-2xl border border-slate-200 bg-slate-50 p-5 shadow-sm"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold text-slate-900">上线准备</h2>
            <p class="mt-1 text-xs text-slate-600">{{ commercialReadiness.stage_label }} · 完成 {{ commercialReadiness.met_count }}/{{ commercialReadiness.total_steps }}</p>
          </div>
          <div class="text-2xl font-bold text-slate-800">{{ commercialReadiness.score }}%</div>
        </div>
        <div class="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <router-link
            v-for="step in commercialReadiness.steps"
            :key="`ready-${step.key}`"
            :to="step.route || '/dashboard'"
            class="rounded-xl border px-3 py-3 text-sm transition"
            :class="step.done ? 'border-emerald-200 bg-emerald-50/60 text-emerald-900' : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'"
          >
            <div class="font-medium">{{ step.done ? '✓' : '○' }} {{ step.label }}</div>
            <div class="mt-1 text-[11px] opacity-80">{{ step.hint }}</div>
          </router-link>
        </div>
      </section>

      <section
        v-if="financeVerdict?.headline && financeVerdict.recommendation !== 'wait_for_data'"
        class="rounded-2xl border border-emerald-200 bg-emerald-50/70 px-4 py-4 shadow-sm"
      >
        <div class="text-xs font-medium text-emerald-700">经营结论</div>
        <p class="mt-2 text-sm font-medium text-emerald-950">{{ financeVerdict.headline }}</p>
        <router-link to="/organization/finance" class="mt-2 inline-block text-xs text-emerald-800 underline">
          去财务中心记录决策 →
        </router-link>
      </section>

      <section
        v-if="showLaunchGuide"
        class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <h2 class="text-sm font-semibold text-slate-900">首次上手</h2>
        <p class="mt-1 text-xs text-slate-600">按顺序完成，即可走通接单到结算。</p>
        <ol class="mt-4 space-y-2 text-sm text-slate-700 list-decimal pl-5">
          <li>
            <router-link class="text-teal-700 hover:underline" to="/organization/parent/workspace?section=worktypes">
              公司设置 → 添加工种并启用执行器
            </router-link>
            <span class="text-xs text-slate-500">（启用后重启服务）</span>
          </li>
          <li>
            <router-link class="text-teal-700 hover:underline" to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary">
              育成建档并派首个正式任务
            </router-link>
          </li>
          <li>
            <router-link class="text-teal-700 hover:underline" :to="firstMemberLink">
              员工工作台提交任务结果
            </router-link>
          </li>
          <li>
            <router-link class="text-teal-700 hover:underline" to="/organization/finance">
              财务页记录收支决策
            </router-link>
          </li>
          <li>
            <router-link class="text-teal-700 hover:underline" to="/organization/intake">
              接单台查看漏斗与结算
            </router-link>
          </li>
        </ol>
      </section>



      <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 class="text-sm font-semibold text-slate-900">主路径</h2>
        <p class="mt-1 text-xs text-slate-600">接单 → 分派 → 员工交付 → 结算入账</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <router-link
            to="/organization/intake?section=create"
            class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 hover:bg-slate-100"
          >
            1. 接单台录入
          </router-link>
          <router-link
            to="/organization/intake"
            class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 hover:bg-slate-100"
          >
            2. 确认分派
          </router-link>
          <router-link
            :to="firstMemberLink"
            class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 hover:bg-slate-100"
          >
            3. 员工交付
          </router-link>
          <router-link
            to="/organization/finance"
            class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 hover:bg-slate-100"
          >
            4. 结算 / 决策
          </router-link>
        </div>
      </section>

      <section v-if="attentionNodes.length" class="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-amber-950">需要关注（{{ attentionNodes.length }}）</h2>
          <span class="text-xs text-amber-800">待提交或待育成师确认</span>
        </div>
        <div class="mt-3 space-y-2">
          <button
            v-for="node in attentionNodes"
            :key="node.node_id"
            type="button"
            class="flex w-full items-start gap-3 rounded-xl border border-amber-200 bg-white px-4 py-3 text-left hover:border-amber-300"
            @click="openNode(node)"
          >
            <span class="mt-1 h-2 w-2 shrink-0 rounded-full" :class="node.status === 'submitted' ? 'bg-violet-500' : 'bg-cyan-500'" />
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-medium text-slate-900">{{ node.title }}</span>
                <span class="rounded-full px-2 py-0.5 text-[10px]" :class="workNodeStatusClass(node.status)">
                  {{ node.status_label }}
                </span>
              </div>
              <div class="mt-1 text-xs text-slate-500">{{ node.member_name }} · {{ node.work_type_title }}</div>
            </div>
          </button>
        </div>
      </section>

      <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-slate-900">最近节点</h2>
          <span class="text-xs text-slate-500">按更新时间排序</span>
        </div>
        <div v-if="!recentNodes.length" class="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
          还没有工作节点。请先在育成师页面派任务。
        </div>
        <div v-else class="mt-3 divide-y divide-slate-100">
          <button
            v-for="node in recentNodes"
            :key="`recent-${node.node_id}`"
            type="button"
            class="flex w-full items-center gap-3 py-3 text-left first:pt-0 last:pb-0 hover:bg-slate-50/80"
            @click="openNode(node)"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-medium text-slate-900">{{ node.title }}</div>
              <div class="mt-0.5 text-xs text-slate-500">{{ node.member_name }} · {{ formatDate(node.updated_at) }}</div>
            </div>
            <span class="shrink-0 rounded-full px-2 py-0.5 text-[10px]" :class="workNodeStatusClass(node.status)">
              {{ node.status_label }}
            </span>
          </button>
        </div>
      </section>

      <section v-if="workTypeSnapshots.length" class="grid gap-3 md:grid-cols-2">
        <button
          v-for="item in workTypeSnapshots"
          :key="item.work_type_id"
          type="button"
          class="rounded-xl border border-slate-200 bg-white px-4 py-4 text-left shadow-sm hover:border-teal-200 hover:bg-teal-50/30"
          @click="openWorkType(item.work_type_id)"
        >
          <div class="font-medium text-slate-900">{{ item.title }}</div>
          <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
            <span>{{ item.memberCount }} 人</span>
            <span v-if="item.activeCount">· {{ item.activeCount }} 进行中</span>
            <span v-if="item.submittedCount" class="text-violet-700">· {{ item.submittedCount }} 待确认</span>
          </div>
        </button>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import MetricStrip, { type MetricStripItem } from '../shell/MetricStrip.vue'
import { getCommercialReadiness, type CommercialReadiness } from '../../api/finance'
import { listUnboundMembers } from '../../utils/companyTree'
import { companyConsoleKey } from '../../composables/companyConsole'
import type { WorkNode } from '../../utils/workNodes'
import { workNodeStatusClass } from '../../utils/workNodes'

const consoleCtx = inject(companyConsoleKey)
const router = useRouter()
const loadError = ref('')
const commercialReadiness = ref<CommercialReadiness | null>(null)

const loading = computed(() => consoleCtx?.loading.value ?? false)
const allNodes = computed(() => consoleCtx?.workNodes.value || [])
const financeVerdict = computed(() => consoleCtx?.financeOverview.value?.commercial_verdict || null)

const workTypeCount = computed(() => consoleCtx?.workTypes.value.length || 0)
const memberCount = computed(() => (
  (consoleCtx?.autonomyStatus.value?.child_members?.items || [])
    .filter((item) => String(item.primary_role || '') !== 'talent_development').length
))

const runningCount = computed(() => allNodes.value.filter((item) => item.status === 'running').length)
const submittedCount = computed(() => allNodes.value.filter((item) => item.status === 'submitted').length)
const archivedCount = computed(() => allNodes.value.filter((item) => item.status === 'archived').length)

const unboundMembers = computed(() => listUnboundMembers(
  consoleCtx?.autonomyStatus.value?.child_members?.items || [],
  consoleCtx?.workTypes.value || [],
))

const showLaunchGuide = computed(() => workTypeCount.value === 0 || memberCount.value === 0)

const intakeFunnel = computed(() => consoleCtx?.autonomyStatus.value?.intake_funnel || {})

const intakeFunnelCards = computed(() => {
  const funnel = intakeFunnel.value
  const counts = funnel.counts || {}
  const currency = funnel.currency || 'CNY'
  const money = (value?: number) => {
    if (value == null || Number.isNaN(Number(value))) return '—'
    return `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${currency}`
  }
  return [
    { key: 'open', label: '待处理', value: funnel.open_count ?? 0 },
    { key: 'pipeline', label: '在途产值', value: money(funnel.pipeline_value) },
    { key: 'delivered', label: '待结算', value: counts.delivered ?? 0 },
    { key: 'settled', label: '已结算', value: money(funnel.settled_value) },
  ]
})

const supplyGrowthCards = computed(() => {
  const members = (consoleCtx?.autonomyStatus.value?.child_members?.items || [])
    .filter((item) => String(item.primary_role || '') !== 'talent_development')
  let commercialCount = 0
  let commercialRevenue = 0
  let reflected = 0
  for (const member of members) {
    const growth = (member as { growth_state?: Record<string, unknown> }).growth_state || {}
    commercialCount += Number(growth.commercial_settled_count || 0) || 0
    commercialRevenue += Number(growth.commercial_settled_revenue || 0) || 0
    const stage = String(member.training_plan?.stage || member.onboarding?.status || '')
    if (stage.includes('reflection') || stage.includes('commercial') || stage.includes('independent')) {
      reflected += 1
    }
  }
  return [
    { key: 'members', label: '在岗员工', value: members.length },
    { key: 'reflected', label: '已有成长阶段', value: reflected },
    { key: 'commercial_n', label: '商业结算单数', value: commercialCount },
    {
      key: 'commercial_rev',
      label: '商业结算产值',
      value: commercialRevenue
        ? commercialRevenue.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
        : '—',
    },
  ]
})

const summaryMetrics = computed<MetricStripItem[]>(() => ([
  { key: 'work_types', label: '工种', value: workTypeCount.value },
  { key: 'members', label: '员工', value: memberCount.value },
  { key: 'intake_open', label: '接单待处理', value: intakeFunnel.value.open_count ?? 0, valueClass: 'text-slate-900' },
  { key: 'running', label: '进行中', value: runningCount.value, valueClass: 'text-cyan-700' },
  {
    key: 'pending',
    label: '待确认 / 已归档',
    value: `${submittedCount.value} / ${archivedCount.value}`,
  },
]))

const firstMember = computed(() => {
  const members = consoleCtx?.autonomyStatus.value?.child_members?.items || []
  return members.find((item) => String(item.primary_role || '') !== 'talent_development')
})

const firstMemberLink = computed(() => {
  const memberId = String(firstMember.value?.member_id || '').trim()
  if (!memberId) {
    return '/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary'
  }
  return `/organization/child/${encodeURIComponent(memberId)}/workspace`
})

const attentionNodes = computed(() => (
  allNodes.value
    .filter((item) => item.status === 'running' || item.status === 'submitted')
    .slice(0, 8)
))

const recentNodes = computed(() => (
  [...allNodes.value]
    .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')))
    .slice(0, 10)
))

const workTypeSnapshots = computed(() => {
  const workTypes = consoleCtx?.workTypes.value || []
  return workTypes.map((workType) => {
    const workTypeId = String(workType.work_type_id || '').trim()
    const nodes = allNodes.value.filter((item) => item.work_type_id === workTypeId)
    const memberIds = new Set(nodes.map((item) => item.member_id))
    return {
      work_type_id: workTypeId,
      title: String(workType.title || workTypeId),
      memberCount: memberIds.size,
      activeCount: nodes.filter((item) => item.status === 'running').length,
      submittedCount: nodes.filter((item) => item.status === 'submitted').length,
    }
  }).filter((item) => item.memberCount > 0 || item.activeCount > 0 || item.submittedCount > 0)
})

const formatDate = (value?: string | null) => {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const openNode = (node: WorkNode) => {
  router.push({
    path: '/dashboard',
    query: {
      scope: 'node',
      node: node.node_id,
      member: node.member_id,
      wt: node.work_type_id,
    },
  })
}

const openWorkType = (workTypeId: string) => {
  router.push({
    path: '/dashboard',
    query: { scope: 'work_type', wt: workTypeId },
  })
}

const retryLoad = async () => {
  loadError.value = ''
  try {
    await consoleCtx?.refreshOverview()
    await loadCommercialReadiness()
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '数据同步失败'
  }
}

const loadCommercialReadiness = async () => {
  try {
    const result = await getCommercialReadiness(consoleCtx?.tenantId.value)
    commercialReadiness.value = result.data || null
  } catch {
    commercialReadiness.value = null
  }
}

onMounted(() => {
  void loadCommercialReadiness()
})
</script>
