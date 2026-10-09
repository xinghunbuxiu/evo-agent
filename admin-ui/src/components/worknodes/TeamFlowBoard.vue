<template>
  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">TEAM WORKFLOW</p>
        <h2 class="mt-1 text-lg font-semibold text-slate-900">团队执行流水</h2>
        <p class="mt-1 text-xs text-slate-500">从岗位分工到任务交付；选择成员或任务查看真实执行记录。</p>
      </div>
      <div class="flex flex-wrap gap-2 text-xs">
        <span class="rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-700">{{ completed.length }} 已归档</span>
        <span class="rounded-full bg-sky-50 px-2.5 py-1 text-sky-700">{{ active.length }} 执行中</span>
        <span class="rounded-full bg-amber-50 px-2.5 py-1 text-amber-700">{{ waiting.length }} 待处理</span>
      </div>
    </div>

    <div class="mt-5 overflow-x-auto pb-2">
      <div class="min-w-[760px]">
        <div class="mx-auto max-w-xs rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center">
          <div class="text-[10px] font-medium uppercase tracking-wider text-slate-400">协调与验收</div>
          <div class="mt-1 text-sm font-semibold text-slate-800">{{ leadName }}</div>
          <div class="mt-1 text-xs text-slate-500">任务协调 · 交付确认 · 复盘归档</div>
        </div>
        <div class="mx-auto h-5 w-px bg-slate-300"></div>
        <div class="grid grid-cols-4 gap-3 border-t border-dashed border-slate-300 pt-4">
          <button
            v-for="member in visibleMembers"
            :key="member.id"
            type="button"
            class="team-member-card group min-w-0 rounded-2xl border border-slate-200 bg-white px-3 py-4 text-left transition hover:-translate-y-1 hover:border-teal-300 hover:shadow-lg"
            @click="openMember(member)"
          >
            <div class="flex flex-col items-center gap-2 text-center">
              <WorkerAvatar :name="member.name" :role="member.role" :level="member.level" />
              <span class="max-w-full truncate text-sm font-semibold text-slate-900">{{ member.name }}</span>
            </div>
            <div class="mt-1 truncate text-[11px] text-slate-500">{{ member.role }}</div>
            <div class="mt-2 inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-medium" :class="member.taskCount ? 'bg-teal-50 text-teal-700' : 'bg-slate-100 text-slate-500'"><span class="h-1.5 w-1.5 rounded-full" :class="member.taskCount ? 'bg-teal-500' : 'bg-slate-400'"></span>{{ member.taskCount ? '关联任务 ' + member.taskCount : '暂无关联任务' }}</div>
            <div class="mt-3 h-1 overflow-hidden rounded-full bg-slate-100">
              <div class="h-full rounded-full bg-teal-600" :style="{ width: member.load + '%' }"></div>
            </div>
            <div class="mt-1 text-[10px] text-slate-400">当前负载 {{ member.load }}%</div>
          </button>
          <div v-if="!visibleMembers.length" class="col-span-4 rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
            暂无岗位成员。创建员工并绑定工种后，这里会显示团队分工。
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4 grid gap-3 lg:grid-cols-3">
      <div v-for="column in columns" :key="column.key" class="min-w-0 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
        <div class="mb-3 flex items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <span class="h-2 w-2 rounded-full" :class="column.dot"></span>
            <h3 class="text-xs font-semibold text-slate-700">{{ column.label }}</h3>
          </div>
          <span class="text-[10px] tabular-nums text-slate-400">{{ column.items.length }}</span>
        </div>
        <div v-if="!column.items.length" class="rounded-lg border border-dashed border-slate-200 bg-white/70 px-3 py-5 text-center text-xs text-slate-400">暂无任务</div>
        <button
          v-for="node in column.items"
          :key="node.node_id"
          type="button"
          class="mb-2 block w-full rounded-lg border border-slate-200 bg-white p-3 text-left transition last:mb-0 hover:border-teal-300 hover:shadow-sm"
          @click="openNode(node)"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="line-clamp-2 text-xs font-semibold leading-5 text-slate-800">{{ node.title }}</span>
            <span class="shrink-0 rounded-full px-2 py-0.5 text-[10px]" :class="statusClass(node.status)">{{ node.status_label || statusLabel(node.status) }}</span>
          </div>
          <div class="mt-2 flex items-center justify-between gap-2 text-[10px] text-slate-500">
            <span class="truncate">{{ node.member_name || node.work_type_title || '待分配' }}</span>
            <span v-if="node.updated_at" class="shrink-0">{{ formatDate(node.updated_at) }}</span>
          </div>
          <div class="mt-2 h-1 overflow-hidden rounded-full bg-slate-100">
            <div class="h-full rounded-full transition-all" :class="node.status === 'archived' || node.status === 'approved' ? 'bg-emerald-500' : node.status === 'running' ? 'bg-teal-600' : 'bg-slate-300'" :style="{ width: progress(node.status) + '%' }"></div>
          </div>
        </button>
      </div>
    </div>
    <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 pt-3 text-[10px] text-slate-400">
      <span class="inline-flex items-center gap-1.5"><span class="h-1.5 w-5 rounded bg-emerald-500"></span>已完成 / 已归档</span>
      <span class="inline-flex items-center gap-1.5"><span class="h-1.5 w-5 rounded bg-teal-600"></span>执行中</span>
      <span class="inline-flex items-center gap-1.5"><span class="h-1.5 w-5 rounded bg-slate-300"></span>待处理 / 待确认</span>
      <span class="ml-auto">状态来自当前工作节点数据</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WorkNode } from '../../utils/workNodes'
import WorkerAvatar from './WorkerAvatar.vue'

type MemberInput = {
  member_id?: string
  name?: string
  display_name?: string
  primary_role?: string
  role?: string
  persona?: { role_label?: string }
  status?: string
  growth_state?: { commercial_settled_count?: number; phase?: string }
  experience_journal?: { card_count?: number }
}

const props = defineProps<{
  nodes: WorkNode[]
  members: MemberInput[]
  leadName?: string
}>()
const emit = defineEmits<{
  (event: 'select-node', nodeId: string): void
  (event: 'select-member', memberId: string): void
}>()

const normalizedMembers = computed(() => props.members
  .filter((item) => String(item.primary_role || '') !== 'talent_development')
  .map((item) => {
    const id = String(item.member_id || '')
    const tasks = props.nodes.filter((node) => String(node.member_id || '') === id)
    return {
      id,
      name: String(item.name || item.display_name || id || '未命名成员'),
      role: String(item.persona?.role_label || roleLabel(item.primary_role || item.role)),
      taskCount: tasks.length,
      level: Math.max(1, Math.min(20, 1 + Math.floor((Number(item.growth_state?.commercial_settled_count || 0) + Number(item.experience_journal?.card_count || 0)) / 3))),
      status: String(item.status || 'active'),
      load: tasks.length ? Math.min(100, Math.max(18, tasks.filter((n) => n.status === 'running').length * 35)) : 8,
    }
  }).filter((item) => item.id))

const visibleMembers = computed(() => normalizedMembers.value.slice(0, 4))
const leadName = computed(() => props.leadName || '育成师 / 团队负责人')
const completed = computed(() => props.nodes.filter((n) => ['archived', 'approved', 'completed', 'done'].includes(String(n.status))).slice(0, 100))
const active = computed(() => props.nodes.filter((n) => ['running', 'submitted'].includes(String(n.status))))
const waiting = computed(() => props.nodes.filter((n) => !['archived', 'approved', 'completed', 'done', 'running', 'submitted'].includes(String(n.status))))
const columns = computed(() => [
  { key: 'done', label: '已完成 · 可复用经验', dot: 'bg-emerald-500', items: props.nodes.filter((n) => ['archived', 'approved', 'completed', 'done'].includes(String(n.status))).slice(0, 5) },
  { key: 'active', label: '执行中 · 待确认', dot: 'bg-teal-600', items: props.nodes.filter((n) => ['running', 'submitted'].includes(String(n.status))).slice(0, 5) },
  { key: 'waiting', label: '待处理 · 待分配', dot: 'bg-slate-400', items: props.nodes.filter((n) => !['archived', 'approved', 'completed', 'done', 'running', 'submitted'].includes(String(n.status))).slice(0, 5) },
])

function roleLabel(value?: string) {
  const labels: Record<string, string> = {
    content_creator: '内容创作', researcher: '研究分析', developer: '研发工程',
    operator: '运营执行', analyst: '数据分析', designer: '视觉设计',
    talent_development: '育成师', sales: '商务拓展',
  }
  const key = String(value || '').trim()
  return labels[key] || key.replace(/_/g, ' ') || '岗位成员'
}

function openNode(node: WorkNode) {
  emit('select-node', node.node_id)
}
function openMember(member: { id: string }) {
  emit('select-member', member.id)
}
function statusLabel(status: unknown) {
  const value = String(status || '')
  if (value === 'running') return '执行中'
  if (value === 'submitted') return '待确认'
  if (['archived', 'approved', 'completed', 'done'].includes(value)) return '已完成'
  return '待处理'
}
function statusClass(status: unknown) {
  const value = String(status || '')
  if (['archived', 'approved', 'completed', 'done'].includes(value)) return 'bg-emerald-50 text-emerald-700'
  if (value === 'running') return 'bg-teal-50 text-teal-700'
  if (value === 'submitted') return 'bg-violet-50 text-violet-700'
  return 'bg-slate-100 text-slate-600'
}
function progress(status: unknown) {
  const value = String(status || '')
  if (['archived', 'approved', 'completed', 'done'].includes(value)) return 100
  if (value === 'submitted') return 82
  if (value === 'running') return 55
  return 12
}
function formatDate(value: unknown) {
  if (!value) return ''
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}
</script>

<style scoped>
.team-member-card { background: linear-gradient(180deg, #fff 0%, #fbfcff 100%); }
.team-member-card:hover { box-shadow: 0 12px 28px -18px rgba(26,54,75,.35); }
</style>
