<script setup lang="ts">
import { computed } from 'vue'
import type { Platform } from '~/logic/types'
import { PLATFORM_LABELS } from '~/logic/platform'

const props = defineProps<{ platform: Platform | null }>()

const colorMap: Record<Platform, string> = {
  douyin: 'bg-zinc-200 text-zinc-800',
}

const cls = computed(() => (props.platform ? colorMap[props.platform] : 'bg-gray-100 text-gray-500'))
const label = computed(() => (props.platform ? PLATFORM_LABELS[props.platform] : '未识别'))
</script>

<template>
  <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" :class="cls">
    {{ label }}
  </span>
</template>
