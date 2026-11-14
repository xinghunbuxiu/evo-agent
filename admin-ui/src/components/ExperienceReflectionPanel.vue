<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-slate-900">Experience Reflection 复盘审核</h2>
        <p class="mt-1 text-sm text-slate-500">提交观察与审核决定分开保存；接受 Reflection 不会直接发布 Skill。</p>
      </div>
      <button
        type="button"
        class="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        :disabled="loading"
        @click="load"
      >
        {{ loading ? '刷新中…' : '刷新队列' }}
      </button>
    </div>

    <p v-if="message" class="rounded-lg border px-3 py-2 text-sm" :class="failed ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-slate-200 bg-slate-50 text-slate-600'" role="status">
      {{ message }}
    </p>

    <div v-if="loading && items.length === 0" class="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
      正在读取 Reflection…
    </div>
    <div v-else-if="items.length === 0" class="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
      当前租户还没有 Reflection 提交
    </div>

    <article
      v-for="item in items"
      :key="item.reflection.id"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="break-all font-mono text-sm font-semibold text-slate-900">{{ item.reflection.id }}</div>
          <div class="mt-1 text-xs text-slate-500">
            Source: {{ item.reflection.metadata?.experience_reflection?.source_experience_id || '-' }}
            · Revision {{ item.reflection.metadata?.experience_reflection?.revision ?? '-' }}
          </div>
          <div class="mt-1 text-xs text-slate-500">
            作者 {{ item.reflection.metadata?.experience_reflection?.author || '-' }}
            · 提交时间 {{ item.reflection.metadata?.experience_reflection?.created_at || '-' }}
          </div>
        </div>
        <span
          class="rounded-full px-2.5 py-1 text-xs font-medium"
          :class="stateClass(item.effective_state)"
        >
          {{ stateLabel(item.effective_state) }}
        </span>
      </div>

      <div class="mt-4">
        <div class="text-xs font-semibold uppercase tracking-wide text-slate-400">Findings</div>
        <pre class="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{{ JSON.stringify(item.reflection.metadata?.experience_reflection?.findings || {}, null, 2) }}</pre>
      </div>

      <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
        <span>来源证据 {{ item.reflection.metadata?.experience_reflection?.source_evidence_refs?.length || 0 }} 条</span>
        <span v-for="evidence in (item.reflection.metadata?.experience_reflection?.source_evidence_refs || [])" :key="evidence" class="rounded bg-slate-100 px-2 py-1 font-mono">
          {{ evidence }}
        </span>
      </div>

      <div v-if="item.decision" class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
        <div>复核人：{{ item.decision.reviewer }} · 时间：{{ item.decision.decision_at }}</div>
        <div v-if="item.decision.reason" class="mt-1">理由：{{ item.decision.reason }}</div>
        <div class="mt-1 text-slate-400">审核记录独立追加，原 Reflection 未被覆盖。</div>
      </div>

      <div v-else class="mt-4 space-y-3 border-t border-slate-100 pt-4">
        <label class="block text-xs font-medium text-slate-600">
          拒绝理由（拒绝时必填）
          <textarea
            v-model="rejectionReasons[item.reflection.id]"
            rows="2"
            class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
            placeholder="说明证据缺口、逻辑问题或不适用条件"
          />
        </label>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg bg-teal-600 px-3 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-50"
            :disabled="busyId === item.reflection.id"
            @click="decide(item, 'accepted')"
          >
            接受 Reflection
          </button>
          <button
            type="button"
            class="rounded-lg border border-rose-200 px-3 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            :disabled="busyId === item.reflection.id"
            @click="decide(item, 'rejected')"
          >
            拒绝
          </button>
        </div>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  decideExperienceReflection,
  getExperienceReflections,
  type ExperienceReflectionQueueItem,
} from '../api/knowledge'

const props = defineProps<{ tenantId: string }>()
const items = ref<ExperienceReflectionQueueItem[]>([])
const loading = ref(false)
const busyId = ref('')
const message = ref('')
const failed = ref(false)
const rejectionReasons = ref<Record<string, string>>({})
let requestVersion = 0

const stateLabels: Record<string, string> = {
  pending: '待审核',
  accepted: '已接受',
  rejected: '已拒绝',
}
const stateClasses: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800',
  accepted: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-rose-100 text-rose-800',
}
const stateLabel = (state: string) => stateLabels[state] || state
const stateClass = (state: string) => stateClasses[state] || 'bg-slate-100 text-slate-700'

const load = async () => {
  const version = ++requestVersion
  const tenant = props.tenantId || 'default'
  loading.value = true
  message.value = ''
  try {
    const response = await getExperienceReflections(tenant)
    if (version !== requestVersion || tenant !== (props.tenantId || 'default')) return
    if (!response.success) {
      failed.value = true
      message.value = response.message || 'Reflection 队列读取失败'
      return
    }
    items.value = response.data?.items || []
    failed.value = false
    message.value = `已读取 ${items.value.length} 条 Reflection`
  } catch (error) {
    if (version !== requestVersion) return
    failed.value = true
    message.value = 'Reflection 队列读取失败，请稍后重试'
    console.error(error)
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

const decide = async (item: ExperienceReflectionQueueItem, decision: 'accepted' | 'rejected') => {
  const reflectionId = item.reflection.id
  const reason = (rejectionReasons.value[reflectionId] || '').trim()
  if (decision === 'rejected' && !reason) {
    failed.value = true
    message.value = '拒绝 Reflection 必须填写理由'
    return
  }
  busyId.value = reflectionId
  message.value = ''
  try {
    const response = await decideExperienceReflection(
      props.tenantId || 'default',
      reflectionId,
      decision,
      reason || undefined,
    )
    if (!response.success) {
      failed.value = true
      message.value = response.message || '审核决定未能保存'
      return
    }
    failed.value = false
    message.value = decision === 'accepted' ? 'Reflection 已接受' : 'Reflection 已拒绝'
    await load()
  } catch (error) {
    failed.value = true
    message.value = '审核决定未能保存，请使用刷新确认状态'
    console.error(error)
  } finally {
    busyId.value = ''
  }
}

watch(() => props.tenantId, () => {
  requestVersion += 1
  items.value = []
  rejectionReasons.value = {}
  void load()
})

onMounted(load)
</script>
