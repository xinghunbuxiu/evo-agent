<template>
  <nav
    class="rounded-xl border border-slate-200 bg-white p-2 shadow-sm"
    :class="orientation === 'vertical'
      ? 'flex flex-col gap-1'
      : 'grid grid-cols-2 gap-1 sm:grid-cols-4'"
  >
    <button
      v-for="item in items"
      :key="item.key"
      type="button"
      class="rounded-lg px-3 py-2.5 text-left text-sm transition"
      :class="item.active
        ? 'bg-teal-50 font-medium text-teal-900 ring-1 ring-teal-200'
        : 'text-slate-600 hover:bg-slate-50'"
      @click="$emit('select', item.key)"
    >
      <div class="flex items-center justify-between gap-2">
        <span>{{ item.title }}</span>
        <span
          v-if="item.badge"
          class="shrink-0 rounded-full px-2 py-0.5 text-[10px]"
          :class="item.badgeClass || 'bg-slate-100 text-slate-600'"
        >
          {{ item.badge }}
        </span>
      </div>
      <p v-if="orientation === 'vertical' && item.description" class="mt-1 text-[11px] leading-4 text-slate-500">
        {{ item.description }}
      </p>
    </button>
  </nav>
</template>

<script setup lang="ts">
export type WorkspaceSubNavItem = {
  key: string
  title: string
  description?: string
  badge?: string
  badgeClass?: string
  active?: boolean
}

withDefaults(defineProps<{
  items: WorkspaceSubNavItem[]
  orientation?: 'vertical' | 'horizontal'
}>(), {
  orientation: 'vertical',
})

defineEmits<{
  select: [key: string]
}>()
</script>
