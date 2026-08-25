<template>
  <div class="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-4 text-sm text-amber-950">
    <div class="font-medium">父节点收件箱</div>
    <div class="mt-1 text-xs text-amber-700">育成官会把巡检和关键培养状态汇报到这里。你现在主要是把要求下发给育成官，再由育成官去推进当前子女。</div>
    <div class="mt-3 rounded-xl border border-amber-200 bg-white/80 p-4">
      <div class="grid gap-3 md:grid-cols-2">
        <div>
          <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-amber-700">Directive</label>
          <select
            :value="parentDirectiveType"
            class="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700"
            @change="emit('update:parentDirectiveType', ($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="item in parentDirectiveTemplates"
              :key="`directive-${item.value}`"
              :value="item.value"
            >
              {{ item.label }}
            </option>
          </select>
        </div>
        <div>
          <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-amber-700">Trainer Target</label>
          <div class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            {{ trainerMemberDraft?.name || '育成官' }} / {{ trainerMemberDraft?.primary_role || 'talent_development' }}
          </div>
          <div class="mt-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
            本次关注子女：{{ selectedChildMemberDraft?.name || selectedChildMemberId || '--' }} / {{ selectedChildMemberDraft?.primary_role || '--' }}
          </div>
        </div>
      </div>
      <div class="mt-3">
        <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-amber-700">Directive Note</label>
        <textarea
          :value="parentMessageDraft"
          rows="3"
          class="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700"
          placeholder="补充你的判断：比如先别扩方向，先把登录环境跑通 / 先把这轮复盘压成最小闭环..."
          @input="emit('update:parentMessageDraft', ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </div>
      <div class="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
        <div class="font-medium text-slate-900">即将发送的父节点指令</div>
        <div class="mt-2 leading-6 whitespace-pre-wrap">{{ parentDirectivePreview.content || '--' }}</div>
      </div>
      <div class="mt-3 flex justify-end">
        <button
          @click="sendParentMessage"
          :disabled="parentMessageSending || !selectedChildMemberId || !trainerMemberDraft?.member_id || !parentDirectivePreview.content.trim()"
          class="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60"
        >
          {{ parentMessageSending ? '发送中...' : '下发给育成官' }}
        </button>
      </div>
    </div>
    <div v-if="!parentInboxMessages.length" class="mt-3 text-xs text-amber-700">当前还没有新的内部汇报</div>
    <div v-else-if="selectedParentDirectiveReceipt" class="mt-3 rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-medium text-emerald-950">当前子女最近指令回执</div>
          <div class="mt-1 text-xs text-emerald-700">这里展示最近一条父节点指令之后，系统观察到的后续动作。</div>
        </div>
        <div class="text-right">
          <div class="text-xs text-emerald-700">{{ selectedParentDirectiveReceipt.status_label }}</div>
          <span
            class="mt-2 inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium"
            :class="directiveReceiptVerdictBadgeClass(selectedParentDirectiveReceipt.execution_verdict)"
          >
            {{ selectedParentDirectiveReceipt.execution_verdict }}
          </span>
        </div>
      </div>
      <div class="mt-3 rounded-lg border border-emerald-200 bg-white px-3 py-3 text-xs text-slate-700">
        <div class="font-medium text-slate-900">{{ selectedParentDirectiveReceipt.title }}</div>
        <div class="mt-2 leading-6 whitespace-pre-wrap">{{ selectedParentDirectiveReceipt.content }}</div>
        <div class="mt-2 text-slate-500">sent {{ formatDate(selectedParentDirectiveReceipt.created_at) }}</div>
      </div>
      <div class="mt-3 rounded-lg border border-emerald-200 bg-white px-3 py-3 text-xs text-emerald-950">
        <div class="font-medium">系统判定</div>
        <div class="mt-2 leading-6">{{ selectedParentDirectiveReceipt.execution_summary }}</div>
      </div>
      <div class="mt-3 grid gap-3 md:grid-cols-3">
        <div class="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-slate-500">子女反馈</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedParentDirectiveReceipt.child_reply || '暂时还没有新的子女反馈' }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-slate-500">育成官响应</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedParentDirectiveReceipt.trainer_reply || '育成官暂时还没有新的响应' }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-slate-500">训练更新</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedParentDirectiveReceipt.training_update || '还没有检测到新的训练播报' }}</div>
        </div>
      </div>
      <div class="mt-3 grid gap-3 md:grid-cols-2">
        <div class="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-slate-500">训练阶段变化</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedParentDirectiveReceipt.stage_change || '暂无变化' }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-slate-500">下一步变化</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedParentDirectiveReceipt.next_action_change || '暂无变化' }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-slate-500">当前专注变化</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedParentDirectiveReceipt.focus_change || '暂无变化' }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-slate-500">复盘沉淀变化</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedParentDirectiveReceipt.reflection_update || '暂无新的复盘沉淀' }}</div>
        </div>
      </div>
      <div v-if="selectedParentDirectiveReceipt.signals.length" class="mt-3 flex flex-wrap gap-2">
        <span
          v-for="signal in selectedParentDirectiveReceipt.signals"
          :key="`directive-receipt-${signal}`"
          class="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] text-emerald-800"
        >
          {{ signal }}
        </span>
      </div>
    </div>
    <div v-else class="mt-3 space-y-3">
      <div
        v-for="message in parentInboxMessages"
        :key="message.message_id"
        class="rounded-lg border px-3 py-3 text-xs text-slate-700"
        :class="parentInboxMessageCardClass(message)"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-medium text-slate-900">{{ message.title || message.message_type || '--' }}</div>
            <div class="mt-1 flex flex-wrap gap-2">
              <span class="rounded-full px-2.5 py-1 text-[11px] font-medium" :class="parentInboxMessageBadgeClass(message)">
                {{ parentInboxMessageTypeLabel(message) }}
              </span>
              <span class="text-slate-500">{{ message.sender_role || message.sender_member_id || '--' }}</span>
              <span v-if="message.metadata?.directive_type" class="rounded-full bg-white/80 px-2.5 py-1 text-[11px] text-slate-600">
                {{ String(message.metadata.directive_type) }}
              </span>
            </div>
          </div>
          <div class="text-slate-500">{{ formatDate(message.created_at) }}</div>
        </div>
        <div class="mt-2 leading-6">{{ message.content || '--' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type GenericRecord = Record<string, any>

defineProps<{
  parentDirectiveType: string
  parentDirectiveTemplates: GenericRecord[]
  trainerMemberDraft: GenericRecord | null
  selectedChildMemberDraft: GenericRecord | null
  selectedChildMemberId: string
  parentMessageDraft: string
  parentDirectivePreview: GenericRecord
  parentMessageSending: boolean
  parentInboxMessages: GenericRecord[]
  selectedParentDirectiveReceipt: GenericRecord | null
  formatDate: (value?: string | null) => string
  sendParentMessage: () => void | Promise<void>
  directiveReceiptVerdictBadgeClass: (verdict?: string | null) => string
  parentInboxMessageCardClass: (message?: GenericRecord) => string
  parentInboxMessageBadgeClass: (message?: GenericRecord) => string
  parentInboxMessageTypeLabel: (message?: GenericRecord) => string
}>()

const emit = defineEmits<{
  'update:parentDirectiveType': [value: string]
  'update:parentMessageDraft': [value: string]
}>()
</script>
