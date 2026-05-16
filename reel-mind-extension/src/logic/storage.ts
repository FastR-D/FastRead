import { useWebExtensionStorage } from '~/composables/useWebExtensionStorage'
import browser from 'webextension-polyfill'
import type { Settings } from './types'
import { DEFAULT_BACKEND_URL, DEFAULT_SETTINGS, LEGACY_SETTINGS_KEY, SETTINGS_KEY } from './constants'

export { DEFAULT_BACKEND_URL, DEFAULT_SETTINGS }

void browser.storage.local.get([SETTINGS_KEY, LEGACY_SETTINGS_KEY]).then((stored) => {
  if (!stored[SETTINGS_KEY] && stored[LEGACY_SETTINGS_KEY])
    return browser.storage.local.set({ [SETTINGS_KEY]: stored[LEGACY_SETTINGS_KEY] })
})

export const { data: settings, dataReady: settingsReady } = useWebExtensionStorage<Settings>(
  SETTINGS_KEY,
  DEFAULT_SETTINGS,
  {
    mergeDefaults: stored => ({
      ...DEFAULT_SETTINGS,
      ...(stored as Partial<Settings>),
    }),
  },
)
