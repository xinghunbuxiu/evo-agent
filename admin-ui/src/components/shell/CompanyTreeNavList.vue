<template>
  <ul class="space-y-0.5">
    <li v-for="node in nodes" :key="node.id">
      <button
        type="button"
        class="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm transition"
        :class="buttonClass(node)"
        :style="{ paddingLeft: `${8 + depth * 12}px` }"
        @click="onClick(node)"
      >
        <span
          v-if="node.children?.length"
          class="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center text-[10px] text-slate-400"
          @click.stop="toggleExpanded(node.id)"
        >
          {{ expanded.has(node.id) ? '▾' : '▸' }}
        </span>
        <span v-else class="mt-0.5 inline-block w-4 shrink-0" />
        <span class="min-w-0 flex-1">
          <span
            class="block truncate"
            :class="node.kind === 'department' || node.kind === 'function' ? 'font-medium text-slate-800' : 'text-slate-700'"
          >
            {{ node.label }}
          </span>
          <span
            v-if="node.subtitle"
            class="mt-0.5 block truncate text-[10px] leading-4 text-slate-400"
          >
            {{ node.subtitle }}
          </span>
        </span>
        <span
          v-if="node.badge"
          class="mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px]"
          :class="badgeClass(node)"
        >
          {{ node.badge }}
        </span>
      </button>
      <CompanyTreeNavList
        v-if="node.children?.length && expanded.has(node.id)"
        :nodes="node.children"
        :depth="depth + 1"
        :selection-id="selectionId"
        @select="$emit('select', $event)"
      />
    </li>
  </ul>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { CompanyTreeNode } from '../../utils/companyTree'

const props = defineProps<{
  nodes: CompanyTreeNode[]
  depth: number
  selectionId: string
}>()

const emit = defineEmits<{
  select: [node: CompanyTreeNode]
}>()

const expanded = ref<Set<string>>(new Set(['departments', 'functions', 'function:trainer']))

const isSelected = (node: CompanyTreeNode) => (
  node.id === props.selectionId
  || (node.kind === 'member' && props.selectionId === `member:${node.member_id}`)
  || (node.kind === 'work_type' && props.selectionId === `work_type:${node.work_type_id}`)
)

const buttonClass = (node: CompanyTreeNode) => {
  if (isSelected(node)) return 'bg-teal-50 text-teal-900 ring-1 ring-teal-200'
  if (node.kind === 'hint') return 'border border-dashed border-slate-200 text-slate-500 hover:bg-slate-50'
  return 'text-slate-700 hover:bg-slate-50'
}

const badgeClass = (node: CompanyTreeNode) => {
  if (node.id === 'functions' || node.id === 'function:trainer') {
    return 'bg-amber-100 text-amber-800'
  }
  return 'bg-slate-100 text-slate-600'
}

const toggleExpanded = (id: string) => {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

const onClick = (node: CompanyTreeNode) => {
  if (node.children?.length && !['work_type', 'member', 'link', 'hint'].includes(node.kind)) {
    toggleExpanded(node.id)
  }
  emit('select', node)
}

watch(() => props.selectionId, (value) => {
  if (value.startsWith('work_type:') || value.startsWith('member:')) {
    expanded.value = new Set([...expanded.value, 'departments'])
  }
  if (value.includes('trainer') || value.startsWith('function:')) {
    expanded.value = new Set([...expanded.value, 'functions', 'function:trainer'])
  }
}, { immediate: true })
</script>
