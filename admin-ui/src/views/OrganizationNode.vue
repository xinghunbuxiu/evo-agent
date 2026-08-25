<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="节点首页"
      :title="selectedNode?.label || '组织节点'"
      description="先看节点身份、当前工作与成长状态，再进入对应工作台。"
      :loading="loading"
      :show-refresh="true"
      refresh-label="刷新节点"
      :back-to="{ path: '/dashboard' }"
      @refresh="loadNode"
    />

    <div v-if="selectedNode" class="space-y-6">
      <section class="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <article class="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">节点身份</div>
              <div class="mt-2 text-2xl font-semibold text-slate-900">{{ selectedNode.kindLabel }}</div>
              <div class="mt-2 text-sm text-slate-500">{{ selectedNode.role }}</div>
            </div>
            <div class="inline-flex rounded-full px-3 py-1 text-[11px] font-medium" :class="attentionMeta.badgeClass">
              {{ attentionMeta.label }}
            </div>
          </div>

          <div class="mt-5 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <div class="text-sm font-semibold text-slate-900">{{ selectedNode.currentWorkLabel || '--' }}</div>
            <div class="mt-2 text-sm leading-6 text-slate-700">{{ selectedNode.headline || selectedNode.description || '--' }}</div>
            <div class="mt-3 text-xs text-slate-500">当前状态 {{ selectedNode.currentWorkStatus || selectedNode.status || '--' }}</div>
          </div>
        </article>

        <div class="grid gap-4 md:grid-cols-3 xl:grid-cols-1">
          <article class="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前状态</div>
            <div class="mt-2 text-lg font-semibold text-slate-900">{{ selectedNode.status || '--' }}</div>
            <div class="mt-1 text-sm text-slate-500">{{ selectedNode.stage || '待安排' }}</div>
          </article>
          <article class="rounded-2xl border border-emerald-200 bg-emerald-50/70 px-5 py-4 shadow-sm">
            <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">最近成长</div>
            <div class="mt-2 text-sm font-medium leading-6 text-slate-900">{{ selectedNode.recentGrowthSummary || '最近还没有新的成长记录。' }}</div>
          </article>
          <article class="rounded-2xl border border-amber-200 bg-amber-50/80 px-5 py-4 shadow-sm">
            <div class="text-xs uppercase tracking-[0.16em] text-amber-700">待处理事项</div>
            <div class="mt-2 text-sm leading-6 text-slate-900">{{ selectedNode.needsAttention || '当前没有额外提醒。' }}</div>
          </article>
        </div>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1.02fr_0.98fr]">
        <section class="space-y-4">
          <div class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)] p-5 shadow-sm">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-lg font-semibold text-slate-900">当前工作</div>
                <div class="mt-1 text-sm text-slate-500">先确认这个节点此刻在干什么，再决定是否需要深入查看细节。</div>
              </div>
              <router-link
                v-if="selectedNode.currentWorkRoute"
                :to="selectedNode.currentWorkRoute"
                class="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                进入当前工作
              </router-link>
            </div>
            <div class="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-4">
              <div class="text-sm font-semibold text-slate-900">{{ selectedNode.currentWorkLabel || '--' }}</div>
              <div class="mt-2 text-sm leading-6 text-slate-700">{{ selectedNode.headline || selectedNode.description || '--' }}</div>
              <div class="mt-3 inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium" :class="attentionMeta.badgeClass">
                {{ selectedNode.currentWorkStatus || selectedNode.status || '--' }}
              </div>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="text-lg font-semibold text-slate-900">最近成长</div>
            <div class="mt-4 rounded-2xl bg-emerald-50 px-4 py-4 text-sm leading-6 text-slate-700">
              {{ selectedNode.recentGrowthSummary || '最近还没有新的成长记录。' }}
            </div>
          </div>

          <div v-if="selectedMemberRuntime?.memory_hub" class="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-lg font-semibold text-slate-900">当前决策</div>
                <div class="mt-1 text-sm text-slate-500">这里看这位成员这轮是怎么想的、优先复用了什么，以及下一步准备怎么做。</div>
              </div>
              <div class="rounded-full bg-cyan-100 px-3 py-1 text-[11px] font-medium text-cyan-800">
                置信度 {{ Math.round((selectedMemberRuntime.memory_hub.decision_confidence || 0) * 100) }}%
              </div>
            </div>
            <div class="mt-4 grid gap-3">
              <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">当前问题</div>
                <div class="mt-2 font-medium text-slate-900">{{ selectedMemberRuntime.memory_hub.decision_intent || '--' }}</div>
              </div>
              <div class="rounded-xl bg-cyan-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">主方案</div>
                <div class="mt-2 font-medium text-slate-900">{{ selectedMemberRuntime.memory_hub.decision_summary?.primary_plan || '--' }}</div>
              </div>
              <div class="rounded-xl bg-amber-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">为什么关注</div>
                <div class="mt-2 font-medium text-slate-900">{{ selectedMemberRuntime.memory_hub.decision_summary?.escalation_reason || selectedMemberRuntime.memory_hub.decision_summary?.stop_reason || '当前没有额外升级提醒。' }}</div>
              </div>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="text-lg font-semibold text-slate-900">节点边界</div>
            <div class="mt-4 rounded-2xl bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-700">
              {{ nodeBoundaryDescription }}
            </div>
          </div>
        </section>

        <section class="space-y-4">
          <div class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,#ffffff_0%,#fffaf0_100%)] p-5 shadow-sm">
            <div class="text-lg font-semibold text-slate-900">当前提醒</div>
            <div class="mt-4 rounded-2xl bg-amber-50 px-4 py-4 text-sm leading-6 text-slate-700">
              {{ selectedNode.needsAttention || '当前没有额外提醒。' }}
            </div>
            <div class="mt-4 grid gap-3 md:grid-cols-2">
              <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">当前阶段</div>
                <div class="mt-2 font-medium text-slate-900">{{ selectedNode.stage || '--' }}</div>
              </div>
              <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">当前状态</div>
                <div class="mt-2 font-medium text-slate-900">{{ selectedNode.status || '--' }}</div>
              </div>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="text-lg font-semibold text-slate-900">可进入的详情</div>
            <div class="mt-4 grid gap-3">
              <router-link
                v-for="entry in nodeWorkspaceEntries"
                :key="entry.title"
                :to="entry.to"
                class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 transition hover:border-slate-300 hover:bg-slate-100"
              >
                <div class="text-sm font-semibold text-slate-900">{{ entry.title }}</div>
                <div class="mt-2 text-sm leading-6 text-slate-600">{{ entry.description }}</div>
              </router-link>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="text-lg font-semibold text-slate-900">节点说明</div>
            <div class="mt-4 rounded-2xl bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-700">
              {{ selectedNode.description || selectedNode.headline || '--' }}
            </div>
          </div>
        </section>
      </div>
    </div>

    <div v-else class="rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-12 text-center text-slate-500">
      当前节点不存在或尚未建立。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import { getAutonomyStatus, getBrainOverview, type AutonomyStatus, type BrainOverview } from '../api/plugins'
import { getFinanceOverview, type FinanceOverview } from '../api/finance'
import { buildOrganizationModel, organizationAttentionMeta, type OrgNode } from '../utils/organization'

const route = useRoute()
const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const loading = ref(false)
const autonomyStatus = ref<AutonomyStatus | null>(null)
const brainOverview = ref<BrainOverview | null>(null)
const financeOverview = ref<FinanceOverview | null>(null)
const organizationModel = computed(() => buildOrganizationModel(
  autonomyStatus.value,
  brainOverview.value,
  financeOverview.value,
))
const orgNodes = computed<OrgNode[]>(() => organizationModel.value.allNodes)
const runtimeMembers = computed(() => autonomyStatus.value?.child_members?.items || [])

const selectedNode = computed<OrgNode | null>(() => {
  const nodeId = String(route.params.nodeId || '').trim()
  return orgNodes.value.find((item) => item.id === nodeId) || null
})

const selectedMemberRuntime = computed(() => {
  const node = selectedNode.value
  if (!node || (node.kind !== 'child' && node.kind !== 'trainer')) return null
  const prefix = node.kind === 'child' ? 'child:' : 'trainer:'
  const memberId = String(node.id || '').replace(prefix, '')
  return runtimeMembers.value.find((item) => String(item.member_id || '') === memberId) || null
})

const attentionMeta = computed(() => (
  organizationAttentionMeta(selectedNode.value?.attentionLevel || 'stable')
))

const nodeWorkspaceEntries = computed(() => {
  const node = selectedNode.value
  if (!node) return []
  const entries = []
  if (node.currentWorkRoute) {
    entries.push({
      title: '进入当前工作详情',
      description: `继续查看 ${node.currentWorkLabel || '当前工作'} 的具体内容与执行详情。`,
      to: node.currentWorkRoute,
    })
  }
  if (node.kind === 'parent') {
    entries.push({
      title: '公司空间',
      description: '查看公司制度、知识资产、组织边界和共享策略。',
      to: '/organization/parent/workspace',
    })
  } else if (node.kind === 'trainer') {
    entries.push({
      title: '育成师空间',
      description: '继续查看带教安排、巡检状态和成长推动详情。',
      to: node.link || '/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary',
    })
  } else if (node.kind === 'child') {
    entries.push({
      title: '员工工作台',
      description: '继续查看这位员工的任务闭环、成长状态和最近沟通。',
      to: node.link || '/organization/child',
    })
  } else {
    entries.push({
      title: '财务看板',
      description: '查看各项目收益、成本与净收益摘要。',
      to: '/organization/finance',
    })
  }
  entries.push({
    title: '返回组织首页',
    description: '回到公司主览，继续查看其他节点和项目状态。',
    to: '/dashboard',
  })
  return entries
})

const nodeBoundaryDescription = computed(() => {
  const node = selectedNode.value
  if (!node) return '--'
  if (node.kind === 'parent') {
    return '公司节点负责方向、制度、资源和组织边界，不直接替具体岗位成员完成工作。'
  }
  if (node.kind === 'trainer') {
    return '育成官负责带教、巡检、复盘和成长推动，不替代员工的专业执行。'
  }
  if (node.kind === 'child') {
    return '员工只对自己的岗位目标负责，专注完成当前工作并持续成长。'
  }
  return '财务属于职能支持层，后续只处理经营结算与资源流转，不进入内容执行。'
})

const loadNode = async () => {
  loading.value = true
  try {
    const [autonomyResult, brainResult, financeResult] = await Promise.all([
      getAutonomyStatus(tenantId.value || 'default'),
      getBrainOverview(tenantId.value || 'default'),
      getFinanceOverview(),
    ])
    autonomyStatus.value = autonomyResult.data || null
    brainOverview.value = brainResult.data || null
    financeOverview.value = financeResult.data || null
  } finally {
    loading.value = false
  }
}

onMounted(loadNode)

watch(() => route.params.nodeId, () => {
  loadNode().catch((error) => {
    console.error('Failed to refresh organization node:', error)
  })
})
</script>
