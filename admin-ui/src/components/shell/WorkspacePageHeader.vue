<template>
  <header class="rounded-2xl border border-slate-200 bg-white px-5 py-5 shadow-sm">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0 flex-1">
        <div class="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">{{ eyebrow }}</div>
        <h1 class="mt-2 text-2xl font-semibold text-slate-900">{{ title }}</h1>
        <p v-if="description" class="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{{ description }}</p>
        <p v-if="hint" class="mt-1 max-w-2xl text-xs leading-5 text-slate-500">{{ hint }}</p>
      </div>
      <div class="flex shrink-0 flex-wrap gap-2">
        <button
          v-if="showRefresh"
          type="button"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-60"
          :disabled="loading"
          @click="$emit('refresh')"
        >
          {{ loading ? '刷新中...' : refreshLabel }}
        </button>
        <router-link
          v-if="backTo"
          :to="backTo"
          class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
        >
          {{ backLabel }}
        </router-link>
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

withDefaults(defineProps<{
  eyebrow: string
  title: string
  description?: string
  hint?: string
  loading?: boolean
  refreshLabel?: string
  showRefresh?: boolean
  backTo?: RouteLocationRaw
  backLabel?: string
}>(), {
  refreshLabel: '刷新',
  showRefresh: true,
  backLabel: '返回总览',
})

defineEmits<{
  refresh: []
}>()
</script>
