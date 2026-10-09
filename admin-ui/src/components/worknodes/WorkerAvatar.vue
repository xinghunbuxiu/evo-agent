<template>
  <span class="worker-avatar" :style="{ '--avatar-accent': palette[variant].accent, '--avatar-shadow': palette[variant].shadow }" :aria-label="name + '的角色形象'" role="img">
    <svg viewBox="0 0 88 96" class="worker-avatar__art" aria-hidden="true">
      <ellipse cx="44" cy="88" rx="25" ry="5" fill="#1f2937" opacity=".10"/>
      <path d="M19 84 Q20 63 34 60 L54 60 Q68 63 69 84Z" fill="var(--avatar-accent)"/>
      <path d="M35 59 L35 69 Q44 77 53 69 L53 59" fill="#f0b99a"/>
      <path d="M26 39 Q23 17 42 14 Q61 12 63 37 L60 51 Q56 64 44 64 Q31 63 27 49Z" fill="#f5c9a8"/>
      <path v-if="variant===1" d="M25 35 Q19 14 39 10 Q58 6 64 29 L58 35 50 20 Q40 30 25 27Z" fill="#d7e9ff" stroke="#8ba9d4" stroke-width="2"/>
      <path v-else-if="variant===2" d="M26 32 Q22 13 42 11 Q60 10 63 31 L54 24 48 17 Q39 29 26 27Z" fill="#8a5a42"/>
      <path v-else-if="variant===3" d="M25 32 Q19 12 40 9 Q59 6 64 29 L58 34 Q53 18 44 18 Q36 28 25 32Z" fill="#292f42"/>
      <path v-else-if="variant===4" d="M26 30 Q22 11 43 10 Q62 11 63 29 L55 23 Q46 29 30 25Z" fill="#d69a45"/>
      <path v-else d="M26 38 Q20 17 39 11 Q57 6 64 25 L62 38 53 25 Q42 32 27 31Z" fill="#43342f"/>
      <circle cx="36" cy="42" r="2.2" fill="#49352f"/><circle cx="52" cy="42" r="2.2" fill="#49352f"/>
      <path d="M39 50 Q44 54 49 50" fill="none" stroke="#bd776b" stroke-width="2" stroke-linecap="round"/>
      <circle cx="30" cy="49" r="3" fill="#e99c91" opacity=".48"/><circle cx="58" cy="49" r="3" fill="#e99c91" opacity=".48"/>
      <path d="M34 62 L44 71 L54 62" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity=".9"/>
      <circle v-if="variant===0" cx="63" cy="21" r="7" fill="#f5c451" stroke="#fff" stroke-width="2"/>
      <path v-if="variant===1" d="M60 56 l4 4 -4 4 -4 -4z" fill="#f5c451"/>
      <path v-if="variant===2" d="M25 59 l-5 8 9 -2z" fill="#f5c451"/>
      <circle v-if="variant===3" cx="63" cy="60" r="5" fill="#9be3d2" stroke="#fff" stroke-width="2"/>
      <path v-if="variant===4" d="M58 17 l3 -6 3 6 6 3 -6 3 -3 6 -3 -6 -6 -3z" fill="#f5c451"/>
    </svg>
    <span class="worker-avatar__level">Lv.{{ level }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{ name: string; role?: string; level?: number }>(), { role: '', level: 1 })
const palette = [
  { accent: '#6c8ee8', shadow: '#dfe8ff' },
  { accent: '#4cae9a', shadow: '#d7f2eb' },
  { accent: '#d99b56', shadow: '#f9e8cf' },
  { accent: '#9a83d8', shadow: '#ebe4ff' },
  { accent: '#e47f88', shadow: '#ffe2e4' },
]
const variant = computed(() => {
  const key = props.name + ':' + props.role
  let hash = 0
  for (let i = 0; i < key.length; i += 1) hash = (hash * 31 + key.charCodeAt(i)) | 0
  return Math.abs(hash) % palette.length
})
</script>

<style scoped>
.worker-avatar { position:relative; display:inline-flex; width:68px; height:76px; flex:0 0 auto; align-items:flex-end; justify-content:center; overflow:visible; border-radius:22px; background:radial-gradient(circle at 50% 24%,#fff 0%,var(--avatar-shadow) 100%); box-shadow:inset 0 1px 0 #ffffffd9,0 5px 12px #26334d0d; }
.worker-avatar__art { width:66px; height:72px; filter:drop-shadow(0 2px 1px #1f293710); }
.worker-avatar__level { position:absolute; right:-5px; bottom:-3px; min-width:25px; border:2px solid white; border-radius:999px; background:var(--avatar-accent); padding:1px 4px; color:white; font-size:8px; font-weight:800; line-height:14px; text-align:center; }
</style>
