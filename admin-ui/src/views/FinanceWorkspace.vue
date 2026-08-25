<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="职能 · 财务"
      title="经营决策中心"
      description="回答「值不值得继续做」：汇总收支、给出商业化建议，并记录你的下一步经营动作。"
      hint="收入可来自接单结算或 analytics 落盘；成本需手工补录后结论才更可靠。"
      :loading="loading"
      refresh-label="刷新财务"
      :back-to="{ path: '/dashboard' }"
      back-label="返回公司总览"
      @refresh="loadFinance"
    >
      <template #actions>
        <router-link
          to="/organization/intake"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          接单台 · 结算
        </router-link>
      </template>
    </WorkspacePageHeader>

    <p v-if="error" class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {{ error }}
    </p>
    <p v-else-if="decisionMessage" class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
      {{ decisionMessage }}
    </p>

    <section
      v-if="commercialVerdict"
      class="rounded-2xl border p-5 shadow-sm"
      :class="verdictPanelClass"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="text-[11px] font-medium uppercase tracking-[0.16em] opacity-80">经营结论</div>
          <h2 class="mt-2 text-lg font-semibold leading-7">{{ commercialVerdict.headline }}</h2>
          <p class="mt-2 text-sm opacity-90">{{ commercialVerdict.recommendation_label }}</p>
        </div>
        <div class="text-right">
          <div class="text-2xl font-bold">{{ commercialVerdict.score }}</div>
          <div class="text-[11px] opacity-80">决策可信度分</div>
          <div class="mt-1 rounded-full px-2.5 py-1 text-[11px]" :class="confidenceBadgeClass">
            {{ confidenceLabel }}
          </div>
        </div>
      </div>
      <ul v-if="commercialVerdict.reasons?.length" class="mt-4 space-y-1 text-sm opacity-90">
        <li v-for="item in commercialVerdict.reasons" :key="item">· {{ item }}</li>
      </ul>
      <ul v-if="commercialVerdict.next_actions?.length" class="mt-3 space-y-1 text-xs opacity-80">
        <li v-for="item in commercialVerdict.next_actions" :key="`next-${item}`">下一步：{{ item }}</li>
      </ul>
    </section>

    <div v-if="loading && !primary?.updated_at" class="rounded-2xl border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
      正在加载财务数据…
    </div>

    <div v-else-if="!primary?.updated_at" class="space-y-4">
      <div class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-5 py-10 text-center text-sm text-slate-600">
        还没有财务数据。请先让员工完成带 analytics 的正式任务。
      </div>
      <section v-if="readiness" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-sm font-semibold text-slate-900">商业化就绪 · {{ readiness.score }}%</h2>
        <p class="mt-1 text-xs text-slate-500">{{ readiness.stage_label }}</p>
        <div class="mt-4 space-y-2">
          <router-link
            v-for="step in readiness.steps"
            :key="step.key"
            :to="step.route || '/dashboard'"
            class="flex items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm transition"
            :class="step.done ? 'border-emerald-200 bg-emerald-50/50 text-emerald-900' : 'border-slate-200 bg-white text-slate-700 hover:border-teal-200'"
          >
            <span>{{ step.done ? '✓' : '○' }} {{ step.label }}</span>
            <span class="text-xs text-slate-500">{{ step.hint }}</span>
          </router-link>
        </div>
      </section>
    </div>

    <template v-else>
      <MetricStrip :items="metricItems" />

      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-sm font-semibold text-slate-900">补录本期成本</h2>
        <p class="mt-1 text-xs text-slate-500">工具、投放、人力分摊等；补录后净收益与经营结论会更准确。</p>
        <div class="mt-4 flex flex-wrap items-end gap-3">
          <label class="block text-sm text-slate-700">
            <span class="mb-1 block text-xs text-slate-500">成本（元）</span>
            <input
              v-model.number="costDraft"
              type="number"
              min="0"
              step="0.01"
              class="w-40 rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
          </label>
          <button
            type="button"
            class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            :disabled="savingCost || costDraft < 0"
            @click="saveCost"
          >
            {{ savingCost ? '保存中...' : '保存成本' }}
          </button>
        </div>
      </section>

      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-sm font-semibold text-slate-900">记录经营决策</h2>
        <p class="mt-1 text-xs text-slate-500">
          主项目 {{ primary.project_id || '--' }} · 周期 {{ primary.period || '--' }}
        </p>
        <textarea
          v-model="decisionNote"
          rows="2"
          class="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700"
          placeholder="可选：写下判断依据，例如「本周阅读涨但收入未跟上，先调选题」"
        />
        <div class="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
            :disabled="savingDecision"
            @click="recordDecision('continue_invest')"
          >
            继续投入
          </button>
          <button
            type="button"
            class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 hover:bg-amber-100 disabled:opacity-50"
            :disabled="savingDecision"
            @click="recordDecision('adjust_strategy')"
          >
            调整策略
          </button>
          <button
            type="button"
            class="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 hover:bg-rose-100 disabled:opacity-50"
            :disabled="savingDecision"
            @click="recordDecision('shrink')"
          >
            收缩投入
          </button>
        </div>
        <p v-if="latestDecision" class="mt-3 text-xs text-slate-500">
          最近决策：{{ decisionActionLabel(latestDecision.action) }}
          · {{ formatDate(latestDecision.created_at) }}
          · 净收益 ¥{{ Number(latestDecision.net || 0).toFixed(2) }}
          <span v-if="latestDecision.note"> · {{ latestDecision.note }}</span>
        </p>
      </section>

      <section v-if="trends.length > 1" class="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="border-b border-slate-100 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-900">周期趋势</h2>
          <p class="mt-1 text-xs text-slate-500">最近 {{ trends.length }} 个周期净收益变化</p>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead class="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th class="px-4 py-2 text-left">周期</th>
                <th class="px-4 py-2 text-right">收入</th>
                <th class="px-4 py-2 text-right">成本</th>
                <th class="px-4 py-2 text-right">净收益</th>
                <th class="px-4 py-2 text-left">判断</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="row in trends" :key="`${row.project_id}-${row.period}`">
                <td class="px-4 py-3 text-slate-700">{{ row.period }}</td>
                <td class="px-4 py-3 text-right">{{ formatMoney(row.revenue) }}</td>
                <td class="px-4 py-3 text-right">{{ formatMoney(row.cost) }}</td>
                <td class="px-4 py-3 text-right font-medium" :class="netClass(row.net)">{{ formatMoney(row.net) }}</td>
                <td class="px-4 py-3 text-slate-600">{{ verdictLabel(row.verdict) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="decisions.length" class="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="border-b border-slate-100 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-900">决策日志</h2>
        </div>
        <div class="divide-y divide-slate-100">
          <article
            v-for="item in decisions.slice(0, 8)"
            :key="item.id"
            class="px-4 py-3 text-sm"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="font-medium text-slate-900">{{ decisionActionLabel(item.action) }}</span>
              <span class="text-xs text-slate-500">{{ formatDate(item.created_at) }}</span>
            </div>
            <div class="mt-1 text-xs text-slate-500">
              {{ item.project_id }} · {{ item.period }} · 净收益 ¥{{ Number(item.net || 0).toFixed(2) }}
            </div>
            <p v-if="item.note" class="mt-2 text-xs leading-5 text-slate-600">{{ item.note }}</p>
          </article>
        </div>
      </section>

      <section class="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="border-b border-slate-100 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-900">各项目明细</h2>
          <p class="mt-1 text-xs text-slate-500">共 {{ items.length }} 个项目</p>
        </div>
        <div class="divide-y divide-slate-100">
          <article
            v-for="item in items"
            :key="item.project_id"
            class="flex flex-wrap items-center gap-3 px-4 py-4"
          >
            <div class="min-w-0 flex-1">
              <div class="font-medium text-slate-900">{{ item.project_id }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ item.period || '--' }} · {{ item.channel || 'channel' }}</div>
              <p v-if="item.headline" class="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">{{ item.headline }}</p>
            </div>
            <div class="text-right text-sm">
              <div class="font-semibold" :class="netClass(item.net)">{{ formatMoney(item.net) }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ verdictLabel(item.verdict) }}</div>
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import MetricStrip, { type MetricStripItem } from '../components/shell/MetricStrip.vue'
import {
  getCommercialReadiness,
  getFinanceOverview,
  recordFinanceDecision,
  updateFinanceCost,
  type CommercialReadiness,
  type FinanceDecision,
  type FinanceOverview,
  type FinanceSummary,
} from '../api/finance'
import { companyConsoleKey } from '../composables/companyConsole'

const consoleCtx = inject(companyConsoleKey)
const loading = ref(false)
const savingDecision = ref(false)
const savingCost = ref(false)
const error = ref('')
const decisionMessage = ref('')
const decisionNote = ref('')
const costDraft = ref(0)
const localOverview = ref<FinanceOverview | null>(null)
const readiness = ref<CommercialReadiness | null>(null)

const overview = computed(() => consoleCtx?.financeOverview.value || localOverview.value)
const primary = computed(() => overview.value?.primary || ({} as FinanceSummary))
const items = computed(() => overview.value?.items || [])
const trends = computed(() => overview.value?.trends || [])
const decisions = computed(() => overview.value?.decisions || [])
const latestDecision = computed(() => overview.value?.latest_decision || null)
const commercialVerdict = computed(() => overview.value?.commercial_verdict || null)

const metricItems = computed<MetricStripItem[]>(() => ([
  {
    key: 'net',
    label: '净收益',
    value: formatMoney(primary.value.net),
    hint: verdictLabel(primary.value.verdict),
    valueClass: netClass(primary.value.net),
  },
  {
    key: 'revenue',
    label: '收入',
    value: formatMoney(primary.value.revenue),
  },
  {
    key: 'cost',
    label: '成本',
    value: formatMoney(primary.value.cost),
  },
  {
    key: 'engagement',
    label: '阅读 / 互动',
    value: primary.value.views || 0,
    hint: `赞 ${primary.value.likes || 0} · 评 ${primary.value.comments || 0}`,
  },
]))

const verdictPanelClass = computed(() => {
  const rec = commercialVerdict.value?.recommendation
  if (rec === 'continue_invest') return 'border-emerald-200 bg-emerald-50/80 text-emerald-950'
  if (rec === 'shrink') return 'border-rose-200 bg-rose-50/80 text-rose-950'
  if (rec === 'wait_for_data') return 'border-slate-200 bg-slate-50 text-slate-800'
  return 'border-amber-200 bg-amber-50/80 text-amber-950'
})

const confidenceLabel = computed(() => {
  const value = commercialVerdict.value?.confidence
  if (value === 'high') return '高可信'
  if (value === 'medium') return '中可信'
  return '低可信'
})

const confidenceBadgeClass = computed(() => {
  const value = commercialVerdict.value?.confidence
  if (value === 'high') return 'bg-white/80 text-emerald-800'
  if (value === 'medium') return 'bg-white/80 text-amber-800'
  return 'bg-white/80 text-slate-600'
})

const formatMoney = (value: number) => {
  const num = Number.isFinite(value) ? value : 0
  return `¥${num.toFixed(2)}`
}

const verdictLabel = (verdict?: string) => {
  if (verdict === 'profitable') return '盈利'
  if (verdict === 'break_even') return '持平'
  if (verdict === 'loss') return '亏损'
  return '待评估'
}

const decisionActionLabel = (action?: string) => {
  if (action === 'continue_invest') return '继续投入'
  if (action === 'shrink') return '收缩投入'
  if (action === 'adjust_strategy') return '调整策略'
  return action || '--'
}

const netClass = (net: number) => {
  if (net > 0) return 'text-emerald-700'
  if (net < 0) return 'text-red-600'
  return 'text-slate-900'
}

const formatDate = (value?: string | null) => {
  if (!value) return '--'
  return value.replace('T', ' ').slice(0, 19)
}

const loadReadiness = async () => {
  try {
    const result = await getCommercialReadiness(consoleCtx?.tenantId.value)
    readiness.value = result.data || null
  } catch {
    readiness.value = null
  }
}

const loadFinance = async () => {
  loading.value = true
  error.value = ''
  try {
    if (consoleCtx?.refreshOverview) {
      await consoleCtx.refreshOverview()
    } else {
      const result = await getFinanceOverview()
      localOverview.value = result.data || null
    }
    await loadReadiness()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '财务数据加载失败'
  } finally {
    loading.value = false
  }
}

const saveCost = async () => {
  const projectId = String(primary.value.project_id || '').trim()
  if (!projectId) {
    error.value = '当前没有可更新成本的主项目'
    return
  }
  savingCost.value = true
  error.value = ''
  try {
    const result = await updateFinanceCost(projectId, Number(costDraft.value) || 0, primary.value.period)
    if (result.code !== 0) {
      error.value = result.message || '成本保存失败'
      return
    }
    decisionMessage.value = `已更新 ${projectId} 成本为 ¥${Number(costDraft.value || 0).toFixed(2)}`
    await loadFinance()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '成本保存失败'
  } finally {
    savingCost.value = false
  }
}

const recordDecision = async (action: FinanceDecision['action']) => {
  const projectId = String(primary.value.project_id || '').trim()
  if (!projectId) {
    error.value = '当前没有可记录决策的主项目'
    return
  }
  savingDecision.value = true
  error.value = ''
  decisionMessage.value = ''
  try {
    const result = await recordFinanceDecision(projectId, action, decisionNote.value.trim(), primary.value.period)
    if (result.code !== 0) {
      error.value = result.message || '决策记录失败'
      return
    }
    decisionMessage.value = `已记录：${decisionActionLabel(action)}（${projectId}）`
    decisionNote.value = ''
    await loadFinance()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '决策记录失败'
  } finally {
    savingDecision.value = false
  }
}

watch(primary, (value) => {
  costDraft.value = Number(value.cost || 0)
}, { immediate: true })

onMounted(() => {
  void loadFinance()
})
</script>
