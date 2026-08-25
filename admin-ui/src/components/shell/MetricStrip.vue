<template>
  <div class="grid gap-3" :class="gridClass">
    <div
      v-for="item in items"
      :key="item.key"
      class="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
    >
      <div class="text-xs uppercase tracking-[0.16em] text-slate-500">{{ item.label }}</div>
      <div class="mt-2 text-2xl font-semibold" :class="item.valueClass || 'text-slate-900'">
        {{ item.value }}
      </div>
      <div v-if="item.hint" class="mt-1 text-xs text-slate-500">{{ item.hint }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type MetricStripItem = {
  key: string
  label: string
  value: string | number
  hint?: string
  valueClass?: string
}

const props = withDefaults(defineProps<{
  items: MetricStripItem[]
  columns?: 2 | 3 | 4 | 5
}>(), {
  columns: 4,
})

const gridClass = computed(() => {
  if (props.columns === 2) return 'sm:grid-cols-2'
  if (props.columns === 3) return 'sm:grid-cols-2 xl:grid-cols-3'
  if (props.columns === 5) return 'sm:grid-cols-2 xl:grid-cols-5'
  return 'sm:grid-cols-2 xl:grid-cols-4'
})
</script>
