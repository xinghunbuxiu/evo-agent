<template>
  <div>
    <DashboardOverview v-if="isOverview" />
    <WorkNodeWorkspace v-else />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DashboardOverview from '../components/worknodes/DashboardOverview.vue'
import WorkNodeWorkspace from '../components/worknodes/WorkNodeWorkspace.vue'

const route = useRoute()
const isOverview = computed(() => {
  const scope = String(route.query.scope || 'overview').trim()
  return !scope || scope === 'overview'
})
</script>
