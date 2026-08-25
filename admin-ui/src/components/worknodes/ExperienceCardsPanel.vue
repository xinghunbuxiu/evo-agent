<template>
  <div class="space-y-3">
    <div v-if="!cards.length" class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
      当前范围还没有经验卡片。任务确认并复盘后会自动生成。
    </div>
    <article
      v-for="card in cards"
      :key="String(card.card_id || card.title)"
      class="rounded-xl border border-slate-200 bg-white px-4 py-4"
    >
      <div class="text-sm font-semibold text-slate-900">{{ card.title || '经验卡片' }}</div>
      <div v-if="card.stage" class="mt-1 text-xs text-slate-500">{{ card.stage }}</div>
      <div v-if="card.summary" class="mt-3 text-sm leading-6 text-slate-700">{{ card.summary }}</div>
      <div v-if="card.current_pattern" class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        模式：{{ card.current_pattern }}
      </div>
      <div v-if="card.professional_risk" class="mt-2 text-xs text-amber-800">
        风险：{{ card.professional_risk }}
      </div>
      <div v-if="card.next_experiment" class="mt-2 text-xs text-teal-800">
        下一步：{{ card.next_experiment }}
      </div>
    </article>
  </div>
</template>

<script setup lang="ts">
import type { WorkNodeExperienceCard } from '../../utils/workNodes'

defineProps<{
  cards: WorkNodeExperienceCard[]
}>()
</script>
