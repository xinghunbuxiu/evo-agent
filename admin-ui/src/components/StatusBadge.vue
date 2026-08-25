<template>
  <span class="px-3 py-1 rounded-full text-xs font-medium" :class="badgeClass">
    {{ status }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: string
}>()

const badgeClass = computed(() => {
  const classes: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    running: 'bg-blue-100 text-blue-800',
    success: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    cancelled: 'bg-gray-100 text-gray-800',
    draft: 'bg-yellow-100 text-yellow-800',
    verified: 'bg-green-100 text-green-800',
    cloud: 'bg-teal-100 text-teal-800'
  }
  return classes[props.status] || 'bg-gray-100 text-gray-800'
})
</script>
