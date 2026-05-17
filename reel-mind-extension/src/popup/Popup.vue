<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDownloaderCookieStatus } from '~/logic/api'
import { syncCookieToBackend } from '~/logic/cookies'
import { DEFAULT_BACKEND_URL, settings, settingsReady } from '~/logic/storage'
import type { DownloaderCookieStatus } from '~/logic/types'

const tabUrl = ref('')
const busy = ref(false)
const loading = ref(true)
const message = ref('')
const error = ref('')
const status = ref<DownloaderCookieStatus | null>(null)

const backendUrl = computed({
  get: () => settings.value.backendUrl || DEFAULT_BACKEND_URL,
  set: value => {
    settings.value.backendUrl = value.trim().replace(/\/$/, '') || DEFAULT_BACKEND_URL
  },
})

const statusTone = computed(() => {
  if (status.value?.valid_looking)
    return 'ok'
  if (status.value?.configured)
    return 'warn'
  return 'idle'
})

const statusText = computed(() => {
  if (status.value?.valid_looking) {
    if (status.value.warning_message)
      return `后端已有 ${status.value.cookie_count} 项 Cookie；${status.value.warning_message}`
    return `后端已有 ${status.value.cookie_count} 项 Cookie`
  }
  if (status.value?.configured)
    return `Cookie 不完整，缺少 ${status.value.missing_keys.join('、') || '关键字段'}`
  return '后端尚未保存抖音 Cookie'
})

const updatedAt = computed(() => {
  if (!status.value?.updated_at)
    return '从未同步'
  const date = new Date(status.value.updated_at)
  if (Number.isNaN(date.getTime()))
    return '时间未知'
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
})

async function loadActiveTab() {
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true })
    tabUrl.value = tab?.url ?? ''
  }
  catch {
    tabUrl.value = ''
  }
}

async function refreshStatus() {
  error.value = ''
  try {
    status.value = await getDownloaderCookieStatus('douyin')
  }
  catch (e) {
    status.value = null
    error.value = `无法连接后端：${(e as Error).message}`
  }
}

async function syncCookie() {
  busy.value = true
  message.value = ''
  error.value = ''
  try {
    const res = await syncCookieToBackend('douyin')
    if (!res.ok) {
      error.value = res.error || '同步失败'
      return
    }
    message.value = `已捕捉并同步 ${res.count} 项抖音 Cookie`
    await refreshStatus()
  }
  finally {
    busy.value = false
  }
}

async function openDouyin() {
  await browser.tabs.create({ url: 'https://www.douyin.com/jingxuan' })
}

async function openWebSettings() {
  await browser.tabs.create({ url: `${backendUrl.value}/settings/download/douyin` })
}

onMounted(async () => {
  await settingsReady
  await loadActiveTab()
  await refreshStatus()
  loading.value = false
})
</script>

<template>
  <main class="w-[360px] bg-slate-50 text-slate-900">
    <header class="border-b border-slate-200 bg-white px-4 py-3">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h1 class="text-base font-semibold leading-tight">
            Reel Mind Cookie Sync
          </h1>
          <p class="mt-1 text-xs text-slate-500">
            抓取抖音 Cookie 并同步到本地后端
          </p>
        </div>
        <span
          class="rounded-full px-2 py-1 text-xs font-medium"
          :class="statusTone === 'ok'
            ? 'bg-emerald-100 text-emerald-700'
            : statusTone === 'warn'
              ? 'bg-amber-100 text-amber-700'
              : 'bg-slate-200 text-slate-600'"
        >
          {{ statusTone === 'ok' ? '可用' : statusTone === 'warn' ? '需检查' : '未同步' }}
        </span>
      </div>
    </header>

    <section class="space-y-3 p-4">
      <label class="block text-xs font-medium text-slate-600">
        后端地址
        <input
          v-model="backendUrl"
          class="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-500"
          placeholder="http://127.0.0.1:3015"
        >
      </label>

      <div class="rounded-lg border border-slate-200 bg-white p-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-sm font-medium">
              抖音 Cookie
            </div>
            <div class="mt-1 text-xs leading-5 text-slate-500">
              {{ loading ? '读取状态中...' : statusText }}
            </div>
          </div>
          <div class="text-right text-xs text-slate-400">
            {{ updatedAt }}
          </div>
        </div>
      </div>

      <div class="rounded-lg border border-slate-200 bg-white p-3">
        <div class="text-xs font-medium text-slate-600">
          当前标签页
        </div>
        <div class="mt-1 truncate text-xs text-slate-500" :title="tabUrl">
          {{ tabUrl || '未读取到当前标签页' }}
        </div>
      </div>

      <button
        class="flex h-10 w-full items-center justify-center rounded-md bg-slate-950 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        :disabled="busy"
        @click="syncCookie"
      >
        {{ busy ? '同步中...' : '捕捉并同步抖音 Cookie' }}
      </button>

      <div class="grid grid-cols-2 gap-2">
        <button class="h-9 rounded-md border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-100" @click="openDouyin">
          打开抖音精选
        </button>
        <button class="h-9 rounded-md border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-100" @click="openWebSettings">
          前端配置页
        </button>
      </div>

      <div v-if="message" class="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
        {{ message }}
      </div>
      <div v-if="error" class="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
        {{ error }}
      </div>

      <p class="text-xs leading-5 text-slate-500">
        扩展只读取浏览器保存的 douyin.com Cookie，并通过本地后端接口写入下载器配置。
      </p>
    </section>
  </main>
</template>
