<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="接单台"
      title="接单与结算"
      description="录入客户或经营任务，推荐人选后分派、交付并结算。"
      hint="按所需能力推荐人选，不绑定固定工种名。"
      :loading="loading"
      refresh-label="刷新接单"
      :back-to="{ path: '/dashboard' }"
      back-label="返回公司总览"
      @refresh="loadAll"
    >
      <template #actions>
        <router-link
          to="/organization/trainer/talent_development_officer/workspace?mode=dispatch&dispatchTab=assign"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          育成派任务
        </router-link>
        <router-link
          to="/organization/finance"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          财务看板
        </router-link>
      </template>
    </WorkspacePageHeader>

    <p v-if="error" class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {{ error }}
    </p>
    <p v-else-if="message" class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
      {{ message }}
    </p>

    <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div
        v-for="card in funnelCards"
        :key="card.key"
        class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
      >
        <div class="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-400">{{ card.label }}</div>
        <div class="mt-2 text-2xl font-semibold text-slate-900">{{ card.value }}</div>
        <div v-if="card.hint" class="mt-1 text-xs text-slate-500">{{ card.hint }}</div>
      </div>
    </section>

    <WorkspaceSubNav
      orientation="horizontal"
      :items="sectionNav"
      @select="onSectionSelect"
    />

    <section v-if="section === 'create'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 class="text-sm font-semibold text-slate-900">新建接单</h2>
      <p class="mt-1 text-xs text-slate-500">老板或客户需求入口。可勾选能力标签；留空则由系统从文案推断。</p>
      <div class="mt-4 grid gap-4 lg:grid-cols-2">
        <label class="block text-sm text-slate-700 lg:col-span-2">
          <span class="mb-1 block text-xs text-slate-500">任务标题</span>
          <input v-model="draft.title" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="例如：本周内容运营交付">
        </label>
        <label class="block text-sm text-slate-700 lg:col-span-2">
          <span class="mb-1 block text-xs text-slate-500">需求描述</span>
          <textarea v-model="draft.description" rows="4" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="交付目标、约束、验收标准…" />
        </label>
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">客户/来源标签</span>
          <input v-model="draft.client_label" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="外包客户 A / 内部经营">
        </label>
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">来源</span>
          <select v-model="draft.source" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
            <option value="outsourcing">外包</option>
            <option value="internal">内部经营</option>
          </select>
        </label>
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">预算（元）</span>
          <input v-model.number="draft.budget" type="number" min="0" step="0.01" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
        </label>
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">报价（元）</span>
          <input v-model.number="draft.quoted_amount" type="number" min="0" step="0.01" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
        </label>
        <label class="block text-sm text-slate-700 lg:col-span-2">
          <span class="mb-1 block text-xs text-slate-500">期望交付（逗号分隔）</span>
          <input v-model="draft.deliverablesText" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="草稿、发布、数据摘要">
        </label>
        <div class="lg:col-span-2">
          <div class="mb-2 text-xs text-slate-500">所需能力（来自工种配置，可多选）</div>
          <div v-if="capabilityOptions.length" class="flex flex-wrap gap-2">
            <button
              v-for="cap in capabilityOptions"
              :key="cap"
              type="button"
              class="rounded-full border px-3 py-1 text-xs transition"
              :class="draft.needed_capabilities.includes(cap)
                ? 'border-teal-300 bg-teal-50 text-teal-800'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'"
              @click="toggleCapability(cap)"
            >
              {{ cap }}
            </button>
          </div>
          <p v-else class="text-xs text-slate-500">尚未从工种配置读到能力目录；可先提交文案，由系统推断。</p>
        </div>
      </div>
      <div class="mt-5 flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          :disabled="creating || !draft.title.trim()"
          @click="submitCreate"
        >
          {{ creating ? '提交中…' : '创建并分析' }}
        </button>
      </div>
    </section>

    <section v-else class="space-y-4">
      <div class="flex flex-wrap items-center gap-2">
        <button
          v-for="tab in statusTabs"
          :key="tab.key"
          type="button"
          class="rounded-full border px-3 py-1 text-xs transition"
          :class="statusFilter === tab.key
            ? 'border-slate-900 bg-slate-900 text-white'
            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'"
          @click="statusFilter = tab.key"
        >
          {{ tab.label }}
          <span v-if="tab.count != null" class="ml-1 opacity-70">{{ tab.count }}</span>
        </button>
      </div>

      <div v-if="loading && !filteredItems.length" class="rounded-2xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
        正在加载接单…
      </div>
      <div v-else-if="!filteredItems.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-5 py-10 text-center text-sm text-slate-600">
        当前筛选下没有接单。去「新建接单」录入第一条商业任务。
      </div>

      <article
        v-for="item in filteredItems"
        :key="item.intake_id"
        class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="text-base font-semibold text-slate-900">{{ item.title || '未命名接单' }}</h3>
              <span class="rounded-full px-2.5 py-0.5 text-[11px]" :class="statusBadgeClass(item.status)">
                {{ statusLabel(item.status) }}
              </span>
            </div>
            <p class="mt-2 text-sm text-slate-600 whitespace-pre-wrap">{{ item.description || '无描述' }}</p>
            <div class="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
              <span v-if="item.client_label">客户：{{ item.client_label }}</span>
              <span>报价 {{ formatMoney(item.quoted_amount ?? item.budget) }} {{ item.currency || 'CNY' }}</span>
              <span v-if="item.member_id">执行人：{{ item.member_id }}</span>
              <span v-if="item.work_type_id">工种：{{ item.work_type_id }}</span>
              <span v-if="item.fulfillment?.primary_operation_type">履约：{{ item.fulfillment.primary_operation_type }}</span>
              <span v-if="item.routing?.is_override" class="text-amber-700">
                已改派{{ item.routing.override_reason ? `：${item.routing.override_reason}` : '' }}
              </span>
            </div>
            <div v-if="item.needed_capabilities?.length" class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="cap in item.needed_capabilities"
                :key="`${item.intake_id}-${cap}`"
                class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600"
              >
                {{ cap }}
              </span>
            </div>
          </div>
          <div class="text-right text-xs text-slate-400">
            <div>{{ item.intake_id }}</div>
            <div class="mt-1">{{ formatTime(item.updated_at || item.created_at) }}</div>
          </div>
        </div>

        <div
          v-if="item.routing?.candidates?.length"
          class="mt-4 rounded-xl border border-slate-100 bg-slate-50/80 p-3"
        >
          <div class="text-xs font-medium text-slate-700">推荐人选</div>
          <ul class="mt-2 space-y-2">
            <li
              v-for="cand in item.routing.candidates.slice(0, 5)"
              :key="`${item.intake_id}-${cand.member_id}`"
              class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-3 py-2 text-xs text-slate-600"
              :class="cand.member_id === item.routing?.recommended_member_id ? 'ring-1 ring-teal-200' : ''"
            >
              <div>
                <span class="font-medium text-slate-800">{{ cand.name || cand.member_id }}</span>
                <span v-if="cand.member_id === item.routing?.recommended_member_id" class="ml-2 text-teal-700">推荐</span>
                <span
                  v-if="(cand.feedback_bonus || 0) !== 0"
                  class="ml-2"
                  :class="(cand.feedback_bonus || 0) > 0 ? 'text-emerald-700' : 'text-amber-700'"
                >
                  反馈{{ (cand.feedback_bonus || 0) > 0 ? '+' : '' }}{{ cand.feedback_bonus }}
                </span>
                <span
                  v-if="(cand.journal_bonus || 0) !== 0"
                  class="ml-2 text-sky-700"
                >
                  经验+{{ cand.journal_bonus }}
                </span>
                <div class="mt-0.5 text-[11px] text-slate-500">
                  分 {{ cand.score ?? 0 }} · {{ (cand.reasons || []).slice(0, 2).join('；') }}
                </div>
              </div>
              <button
                v-if="canAssign(item)"
                type="button"
                class="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                :disabled="busyId === item.intake_id"
                @click="doAssign(item, cand.member_id)"
              >
                分派此人
              </button>
            </li>
          </ul>
        </div>

        <div
          v-if="item.fulfillment?.artifacts?.length"
          class="mt-4 rounded-xl border border-teal-100 bg-teal-50/50 p-3"
        >
          <div class="text-xs font-medium text-teal-900">
            履约产物
            <span v-if="item.fulfillment.status" class="ml-2 font-normal text-teal-700">
              {{ item.fulfillment.status }}
            </span>
          </div>
          <ul class="mt-2 space-y-1">
            <li
              v-for="(art, index) in item.fulfillment.artifacts.slice(0, 5)"
              :key="`${item.intake_id}-art-${index}`"
              class="break-all text-[11px] text-teal-800"
            >
              {{ art.kind || 'file' }} · {{ art.path || art.label || '--' }}
            </li>
          </ul>
        </div>

        <div class="mt-4 flex flex-wrap gap-2">
          <button
            v-if="canAnalyze(item)"
            type="button"
            class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            :disabled="busyId === item.intake_id"
            @click="doAnalyze(item)"
          >
            重新分析
          </button>
          <button
            v-if="canAssign(item) && item.routing?.recommended_member_id"
            type="button"
            class="rounded-lg bg-teal-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-600 disabled:opacity-50"
            :disabled="busyId === item.intake_id"
            @click="doAssign(item, item.routing.recommended_member_id)"
          >
            确认推荐并分派
          </button>
          <router-link
            v-if="item.member_id"
            :to="`/organization/child/${item.member_id}/workspace?tab=tasks`"
            class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            打开员工工作台
          </router-link>
          <div v-if="canSettle(item)" class="flex flex-wrap items-center gap-2">
            <input
              v-model.number="settleDrafts[item.intake_id]"
              type="number"
              min="0"
              step="0.01"
              class="w-28 rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
              :placeholder="String(item.quoted_amount ?? item.budget ?? '')"
            >
            <button
              type="button"
              class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              :disabled="busyId === item.intake_id"
              @click="doSettle(item)"
            >
              结算入账
            </button>
          </div>
          <button
            v-if="canCancel(item)"
            type="button"
            class="rounded-lg border border-rose-200 px-3 py-1.5 text-xs text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            :disabled="busyId === item.intake_id"
            @click="doCancel(item)"
          >
            取消
          </button>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav, { type WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import {
  analyzeIntake,
  assignIntake,
  cancelIntake,
  createIntake,
  getIntakePolicies,
  listIntakes,
  settleIntake,
  type IntakeFunnel,
  type IntakeItem,
} from '../api/intake'

const route = useRoute()
const router = useRouter()
const tenantId = 'default'

const loading = ref(false)
const creating = ref(false)
const busyId = ref('')
const error = ref('')
const message = ref('')
const items = ref<IntakeItem[]>([])
const funnel = ref<IntakeFunnel>({})
const capabilityOptions = ref<string[]>([])
const statusFilter = ref<string>('open')
const settleDrafts = reactive<Record<string, number | null>>({})

const draft = reactive({
  title: '',
  description: '',
  client_label: '',
  source: 'outsourcing',
  budget: null as number | null,
  quoted_amount: null as number | null,
  deliverablesText: '',
  needed_capabilities: [] as string[],
})

const section = computed(() => {
  const raw = String(route.query.section || 'board').trim()
  return raw === 'create' ? 'create' : 'board'
})

const sectionNav = computed<WorkspaceSubNavItem[]>(() => [
  {
    key: 'board',
    title: '漏斗看板',
    description: '在途与结算',
    active: section.value === 'board',
  },
  {
    key: 'create',
    title: '新建接单',
    description: '商业任务入口',
    active: section.value === 'create',
  },
])

function onSectionSelect(key: string) {
  router.replace({ query: { ...route.query, section: key } })
}

const counts = computed(() => funnel.value.counts || {})

const funnelCards = computed(() => [
  { key: 'open', label: '待处理', value: funnel.value.open_count ?? 0, hint: 'received / analyzing / assigned / in_progress' },
  { key: 'pipeline', label: '在途产值', value: formatMoney(funnel.value.pipeline_value), hint: funnel.value.currency || 'CNY' },
  { key: 'delivered', label: '已交付', value: counts.value.delivered ?? 0, hint: '待结算' },
  { key: 'settled', label: '已结算', value: formatMoney(funnel.value.settled_value), hint: '财务可见' },
])

const statusTabs = computed(() => [
  { key: 'open', label: '进行中', count: funnel.value.open_count },
  { key: 'delivered', label: '待结算', count: counts.value.delivered },
  { key: 'settled', label: '已结算', count: counts.value.settled },
  { key: 'all', label: '全部', count: funnel.value.item_count },
])

const filteredItems = computed(() => {
  const list = items.value
  if (statusFilter.value === 'all') return list
  if (statusFilter.value === 'open') {
    return list.filter((item) => ['received', 'analyzing', 'assigned', 'in_progress'].includes(String(item.status || '')))
  }
  return list.filter((item) => String(item.status || '') === statusFilter.value)
})

function formatMoney(value: number | null | undefined) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function formatTime(value?: string | null) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 19)
}

function statusLabel(status?: string) {
  const map: Record<string, string> = {
    received: '已接收',
    analyzing: '分析中',
    assigned: '已分派',
    in_progress: '执行中',
    delivered: '已交付',
    settled: '已结算',
    cancelled: '已取消',
  }
  return map[String(status || '')] || status || '未知'
}

function statusBadgeClass(status?: string) {
  const key = String(status || '')
  if (key === 'settled') return 'bg-emerald-50 text-emerald-700'
  if (key === 'delivered') return 'bg-amber-50 text-amber-800'
  if (key === 'cancelled') return 'bg-rose-50 text-rose-700'
  if (key === 'in_progress' || key === 'assigned') return 'bg-teal-50 text-teal-800'
  return 'bg-slate-100 text-slate-600'
}

function canAnalyze(item: IntakeItem) {
  return !['settled', 'cancelled'].includes(String(item.status || ''))
}

function canAssign(item: IntakeItem) {
  return ['received', 'analyzing', 'assigned'].includes(String(item.status || ''))
}

function canSettle(item: IntakeItem) {
  return ['delivered', 'in_progress', 'assigned'].includes(String(item.status || ''))
}

function canCancel(item: IntakeItem) {
  return !['settled', 'cancelled'].includes(String(item.status || ''))
}

function toggleCapability(cap: string) {
  const idx = draft.needed_capabilities.indexOf(cap)
  if (idx >= 0) draft.needed_capabilities.splice(idx, 1)
  else draft.needed_capabilities.push(cap)
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [listRes, policyRes] = await Promise.all([
      listIntakes({ tenant_id: tenantId }),
      getIntakePolicies(),
    ])
    if (listRes.code !== 0) throw new Error(listRes.message || '加载接单失败')
    items.value = listRes.data?.items || []
    funnel.value = listRes.data?.funnel || {}
    const caps = (policyRes.data?.capabilities || [])
      .map((item) => String(item.capability || '').trim())
      .filter(Boolean)
    capabilityOptions.value = caps
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  creating.value = true
  error.value = ''
  message.value = ''
  try {
    const deliverables = draft.deliverablesText
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean)
    const res = await createIntake({
      tenant_id: tenantId,
      title: draft.title.trim(),
      description: draft.description.trim(),
      client_label: draft.client_label.trim() || undefined,
      source: draft.source,
      budget: draft.budget,
      quoted_amount: draft.quoted_amount,
      expected_deliverables: deliverables,
      needed_capabilities: [...draft.needed_capabilities],
      auto_analyze: true,
    })
    if (res.code !== 0) throw new Error(res.message || '创建失败')
    message.value = '接单已创建，已完成初析'
    draft.title = ''
    draft.description = ''
    draft.client_label = ''
    draft.budget = null
    draft.quoted_amount = null
    draft.deliverablesText = ''
    draft.needed_capabilities = []
    await loadAll()
    router.replace({ query: { ...route.query, section: 'board' } })
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建失败'
  } finally {
    creating.value = false
  }
}

async function doAnalyze(item: IntakeItem) {
  busyId.value = item.intake_id
  error.value = ''
  try {
    const res = await analyzeIntake(item.intake_id, { tenant_id: tenantId })
    if (res.code !== 0) throw new Error(res.message || '分析失败')
    message.value = '路由分析已更新'
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '分析失败'
  } finally {
    busyId.value = ''
  }
}

async function doAssign(item: IntakeItem, memberId?: string | null) {
  if (!memberId) return
  const recommended = String(item.routing?.recommended_member_id || '').trim()
  const isOverride = Boolean(recommended && recommended !== memberId)
  let overrideReason: string | undefined
  if (isOverride) {
    const typed = window.prompt(
      '你改派了系统推荐人选。请简短说明原因（会写入路由反馈，供后续分析加权）：',
      '负载/能力更匹配',
    )
    if (typed == null) return
    overrideReason = typed.trim() || 'trainer_manual_override'
  }
  busyId.value = item.intake_id
  error.value = ''
  try {
    const res = await assignIntake(item.intake_id, {
      tenant_id: tenantId,
      member_id: memberId,
      override_reason: overrideReason,
    })
    if (res.code !== 0) throw new Error(res.message || '分派失败')
    message.value = isOverride ? '已改派并记录原因；正式任务已创建' : '已按推荐分派并创建正式任务'
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '分派失败'
  } finally {
    busyId.value = ''
  }
}

async function doSettle(item: IntakeItem) {
  busyId.value = item.intake_id
  error.value = ''
  try {
    const drafted = settleDrafts[item.intake_id]
    const settledAmount = drafted != null && !Number.isNaN(Number(drafted))
      ? Number(drafted)
      : (item.quoted_amount ?? item.budget ?? null)
    const res = await settleIntake(item.intake_id, {
      tenant_id: tenantId,
      settled_amount: settledAmount,
      note: `接单结算：${item.title || item.intake_id}`,
    })
    if (res.code !== 0) throw new Error(res.message || '结算失败')
    message.value = '已结算并记入财务'
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '结算失败'
  } finally {
    busyId.value = ''
  }
}

async function doCancel(item: IntakeItem) {
  busyId.value = item.intake_id
  error.value = ''
  try {
    const res = await cancelIntake(item.intake_id, { tenant_id: tenantId, reason: '人工取消' })
    if (res.code !== 0) throw new Error(res.message || '取消失败')
    message.value = '接单已取消'
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '取消失败'
  } finally {
    busyId.value = ''
  }
}

watch(
  () => route.query.section,
  () => {
    /* section computed from route */
  },
)

onMounted(loadAll)
</script>
