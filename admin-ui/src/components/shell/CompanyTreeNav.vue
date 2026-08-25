<template>
  <div class="flex h-full flex-col">
    <div class="border-b border-slate-100 px-3 py-3">
      <div class="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">公司导航</div>
    </div>
    <nav class="flex-1 overflow-y-auto px-2 py-2">
      <CompanyTreeNavList
        :nodes="nodes"
        :depth="0"
        :selection-id="selectionId"
        @select="$emit('select', $event)"
      />
    </nav>
  </div>
</template>

<script setup lang="ts">
import type { CompanyTreeNode } from '../../utils/companyTree'
import CompanyTreeNavList from './CompanyTreeNavList.vue'

defineProps<{
  nodes: CompanyTreeNode[]
  selectionId: string
}>()

defineEmits<{
  select: [node: CompanyTreeNode]
}>()
</script>
