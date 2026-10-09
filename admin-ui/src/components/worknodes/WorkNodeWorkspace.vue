<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <header class="rounded-2xl border border-slate-200 bg-white px-5 py-5 shadow-sm">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">{{ headerEyebrow }}</div>
          <h1 class="mt-2 text-2xl font-semibold text-slate-900">{{ headerTitle }}</h1>
          <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{{ headerDescription }}</p>
        </div>
        <button
          v-if="scope !== 'overview'"
          type="button"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
          @click="goOverview"
        >
          返回总览
        </button>
        <div v-if="stats.length" class="flex flex-wrap gap-2">
          <span
            v-for="item in stats"
            :key="item.label"
            class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700"
          >
            {{ item.label }} {{ item.value }}
          </span>
        </div>
      </div>
    </header>

    <div class="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div class="flex flex-wrap gap-1 border-b border-slate-100 px-3 py-2">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="rounded-lg px-3 py-2 text-sm font-medium transition"
          :class="activeTab === tab.key ? 'bg-teal-50 text-teal-800' : 'text-slate-600 hover:bg-slate-50'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span v-if="tab.count !== undefined" class="ml-1 text-xs text-slate-400">({{ tab.count }})</span>
        </button>
      </div>

      <div class="p-4 lg:p-5">
        <div v-show="activeTab === 'timeline'" class="grid gap-5 xl:grid-cols-[1fr_360px]">
          <NodeTimelineList
            :nodes="filteredNodes"
            :selected-node-id="selectedNodeId"
            @select="selectNode"
          />
          <NodePhasePanel
            v-if="selectedNode"
            :node="selectedNode"
          />
          <div
            v-else
            class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500"
          >
            选择一条节点，查看从思考到归档的完整流程。
          </div>
        </div>

        <ExperienceCardsPanel
          v-show="activeTab === 'experience'"
          :cards="experienceCards"
        />

        <SkillsPlaceholderPanel
          v-show="activeTab === 'skills'"
          :work-type-id="workTypeId || selectedNode?.work_type_id"
          :member-id="memberId || selectedNode?.member_id"
        />

        <ArchivePlaceholderPanel
          v-show="activeTab === 'archive'"
          :nodes="filteredNodes"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { companyConsoleKey } from '../../composables/companyConsole'
import { collectExperienceCards, filterWorkNodes } from '../../utils/workNodes'
import NodeTimelineList from './NodeTimelineList.vue'
import NodePhasePanel from './NodePhasePanel.vue'
import ExperienceCardsPanel from './ExperienceCardsPanel.vue'
import SkillsPlaceholderPanel from './SkillsPlaceholderPanel.vue'
import ArchivePlaceholderPanel from './ArchivePlaceholderPanel.vue'

const route = useRoute()
const router = useRouter()
const consoleCtx = inject(companyConsoleKey)

const activeTab = ref<'timeline' | 'experience' | 'skills' | 'archive'>('timeline')

const scope = computed(() => String(route.query.scope || 'overview').trim())
const workTypeId = computed(() => String(route.query.wt || '').trim())
const memberId = computed(() => String(route.query.member || '').trim())
const selectedNodeId = computed(() => String(route.query.node || '').trim())

const filteredNodes = computed(() => {
  const all = consoleCtx?.workNodes.value || []
  if (scope.value === 'member' && memberId.value) {
    return filterWorkNodes(all, { member_id: memberId.value })
  }
  if (scope.value === 'work_type' && workTypeId.value) {
    return filterWorkNodes(all, { work_type_id: workTypeId.value })
  }
  if (scope.value === 'node' && selectedNodeId.value) {
    return filterWorkNodes(all, { node_id: selectedNodeId.value })
  }
  return all
})

const selectedNode = computed(() => (
  filteredNodes.value.find((item) => item.node_id === selectedNodeId.value)
  || filteredNodes.value[0]
  || null
))

const experienceCards = computed(() => collectExperienceCards(filteredNodes.value))
const selectedMemberProfile = computed(() => (
  consoleCtx?.autonomyStatus.value?.child_members?.items?.find(
    (item) => String(item.member_id || '') === memberId.value,
  ) || null
))

const headerEyebrow = computed(() => {
  if (scope.value === 'member') return '员工节点'
  if (scope.value === 'work_type') return '工种节点'
  return '公司节点'
})

const WORK_TYPE_TITLE_FALLBACK: Record<string, string> = {
  __unbound__: '未绑定工种',
}

const headerTitle = computed(() => {
  if (scope.value === 'member') {
    return selectedMemberProfile.value?.name
      || selectedNode.value?.member_name
      || memberId.value
      || '员工工作档案'
  }
  if (scope.value === 'work_type') {
    return filteredNodes.value[0]?.work_type_title
      || WORK_TYPE_TITLE_FALLBACK[workTypeId.value]
      || workTypeId.value
      || '工种流水'
  }
  return '工作节点总览'
})

const headerDescription = computed(() => {
  if (scope.value === 'member') {
    const role = selectedMemberProfile.value?.persona?.role_label
    const focus = selectedMemberProfile.value?.growth_state?.current_focus
    const nextGoal = selectedMemberProfile.value?.growth_state?.next_goal
    const details = [
      role ? `岗位：${role}` : '',
      focus ? `当前重点：${focus}` : '',
      nextGoal ? `下一目标：${nextGoal}` : '',
    ].filter(Boolean).join(' · ')
    return details
      ? `${details}。查看该员工从思考、执行、提交到经验沉淀的完整节点流水。`
      : '查看该员工从思考、执行、提交到经验沉淀的完整节点流水。'
  }
  if (scope.value === 'work_type') {
    return '聚合该工种下所有员工的任务节点，按时间查看经验与归档状态。'
  }
  return '按节点记录工作流程：思考 → 分配 → 执行 → 提交 → 确认 → 沉淀 → Gitee 归档。'
})

const stats = computed(() => {
  const nodes = filteredNodes.value
  return [
    { label: '节点', value: nodes.length },
    { label: '进行中', value: nodes.filter((item) => item.status === 'running' || item.status === 'submitted').length },
    { label: '已归档', value: nodes.filter((item) => item.status === 'archived').length },
  ]
})

const tabs = computed(() => ([
  { key: 'timeline' as const, label: '节点流水', count: filteredNodes.value.length },
  { key: 'experience' as const, label: '经验', count: experienceCards.value.length },
  { key: 'skills' as const, label: '技能', count: undefined },
  { key: 'archive' as const, label: '归档', count: nodesArchivedCount.value },
]))

const nodesArchivedCount = computed(() => (
  filteredNodes.value.filter((item) => item.status === 'archived' || item.status === 'approved').length
))

const selectNode = (nodeId: string) => {
  if (selectedNodeId.value === nodeId) return
  router.push({
    path: '/dashboard',
    query: {
      ...route.query,
      scope: scope.value === 'overview' ? 'node' : scope.value,
      node: nodeId,
      wt: workTypeId.value || undefined,
      member: memberId.value || undefined,
    },
  })
}

const goOverview = () => {
  router.push({ path: '/dashboard', query: {} })
}

watch(filteredNodes, (nodes) => {
  if (!nodes.length) return
  if (!selectedNodeId.value || !nodes.some((item) => item.node_id === selectedNodeId.value)) {
    selectNode(nodes[0].node_id)
  }
}, { immediate: true })
</script>
